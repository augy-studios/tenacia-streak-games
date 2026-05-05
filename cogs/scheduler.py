"""
Scheduler cog — SQLite-based task runner.
Checks every 60 seconds for due tasks.
Supports: daily_prompt
"""
import discord
import asyncio
import json
import logging
from discord import app_commands
from discord.ext import commands, tasks
from utils.db import get_db, now_ts
from utils.settings import is_enabled, get_channel
from utils.embeds import success_embed, warning_embed, danger_embed, base_embed

log = logging.getLogger("tenacia.scheduler")

TASK_TYPES = ["daily_prompt"]
DEFAULT_INTERVALS = {
    "daily_prompt": 86400,  # 24 hours
}


class Scheduler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    @tasks.loop(seconds=60)
    async def tick(self):
        now = now_ts()
        async with get_db() as db:
            due = await db.execute_fetchall(
                "SELECT * FROM scheduled_tasks WHERE next_run <= ?", (now,)
            )
        for task in due:
            try:
                await self.run_task(task)
            except Exception as e:
                log.error(f"Task {task['id']} ({task['task_type']}) failed: {e}")

    @tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    async def run_task(self, task):
        gid = task["guild_id"]
        task_type = task["task_type"]
        interval = task["interval_secs"]
        now = now_ts()

        if task_type == "daily_prompt":
            if not await is_enabled(gid, "daily_prompt"):
                return
            habits_cog = self.bot.cogs.get("Habits")
            if not habits_cog:
                return
            channel_id = await get_channel(gid, "daily_prompt")
            guild = self.bot.get_guild(gid)
            if not guild:
                return
            channel = guild.get_channel(channel_id) if channel_id else None
            if not channel:
                # Fallback: find first text channel the bot can write in
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break
            if not channel:
                return

            from cogs.habits import fetch_prompt
            prompt_text = await fetch_prompt()
            async with get_db() as db:
                cursor = await db.execute(
                    "INSERT INTO daily_prompts (guild_id, prompt_text, posted_at) VALUES (?,?,?)",
                    (gid, prompt_text, now)
                )
                prompt_id = cursor.lastrowid
                await db.commit()

            embed = base_embed(
                "📝 Daily Prompt",
                f"{prompt_text}\n\n"
                f"Use `/prompt respond` to earn your point!\n"
                f"*Prompt ID: `{prompt_id}`*",
            )
            msg = await channel.send(embed=embed)
            async with get_db() as db:
                await db.execute("UPDATE daily_prompts SET message_id=? WHERE id=?", (msg.id, prompt_id))
                await db.commit()

        # Reschedule task
        async with get_db() as db:
            await db.execute(
                "UPDATE scheduled_tasks SET next_run=? WHERE id=?",
                (now + interval, task["id"])
            )
            await db.commit()
        log.info(f"Ran task {task['id']} ({task_type}) for guild {gid}, next in {interval}s")

    # ────────────────────────────────────────────────────────────────
    # Admin commands
    # ────────────────────────────────────────────────────────────────

    schedule = app_commands.Group(name="schedule", description="Manage scheduled tasks.")

    @schedule.command(name="add", description="Schedule a recurring task for this server.")
    @app_commands.describe(
        task="Which task to schedule",
        interval_hours="How often to run (hours, default 24)",
        delay_minutes="When to run the first time from now (minutes, default 0)",
    )
    @app_commands.choices(task=[app_commands.Choice(name=t, value=t) for t in TASK_TYPES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_add(
        self,
        interaction: discord.Interaction,
        task: app_commands.Choice[str],
        interval_hours: int = 24,
        delay_minutes: int = 0,
    ):
        gid = interaction.guild_id
        now = now_ts()
        next_run = now + delay_minutes * 60
        interval_secs = interval_hours * 3600

        async with get_db() as db:
            existing = await db.execute_fetchall(
                "SELECT id FROM scheduled_tasks WHERE guild_id=? AND task_type=?", (gid, task.value)
            )
            if existing:
                return await interaction.response.send_message(
                    embed=warning_embed("Already Scheduled", f"**{task.value}** is already scheduled. Remove it first with `/schedule remove`."),
                    ephemeral=True
                )
            await db.execute(
                "INSERT INTO scheduled_tasks (guild_id, task_type, next_run, interval_secs) VALUES (?,?,?,?)",
                (gid, task.value, next_run, interval_secs)
            )
            await db.commit()

        await interaction.response.send_message(
            embed=success_embed(
                "Task Scheduled",
                f"**{task.value}** will run every **{interval_hours}h**, starting in **{delay_minutes}m**."
            ),
            ephemeral=True
        )

    @schedule.command(name="remove", description="Remove a scheduled task.")
    @app_commands.describe(task="Which task to remove")
    @app_commands.choices(task=[app_commands.Choice(name=t, value=t) for t in TASK_TYPES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_remove(self, interaction: discord.Interaction, task: app_commands.Choice[str]):
        gid = interaction.guild_id
        async with get_db() as db:
            result = await db.execute(
                "DELETE FROM scheduled_tasks WHERE guild_id=? AND task_type=?", (gid, task.value)
            )
            await db.commit()
        if result.rowcount == 0:
            return await interaction.response.send_message(
                embed=warning_embed("Not Found", f"**{task.value}** is not scheduled."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success_embed("Task Removed", f"**{task.value}** has been unscheduled."), ephemeral=True
        )

    @schedule.command(name="list", description="View all scheduled tasks for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_list(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM scheduled_tasks WHERE guild_id=?", (gid,)
            )
        if not rows:
            return await interaction.response.send_message(
                embed=warning_embed("No Tasks", "No tasks are scheduled for this server."), ephemeral=True
            )
        embed = base_embed("⏰ Scheduled Tasks")
        for r in rows:
            now = now_ts()
            secs_until = max(0, int(r["next_run"] - now))
            h, rem = divmod(secs_until, 3600)
            m = rem // 60
            embed.add_field(
                name=f"📋 {r['task_type']}",
                value=f"Every **{r['interval_secs']//3600}h** · Next run in **{h}h {m}m**",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
