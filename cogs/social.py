"""
Social cog — Hype Keeper, Loyal Opposition, Streak Breaker.
"""
import discord
import json
from discord import app_commands
from discord.ext import commands
from utils.db import get_db, now_ts, ts_to_dt
from utils.settings import is_enabled
from utils.embeds import (
    warning_embed, not_enabled_embed, leaderboard_embed,
    base_embed, COLOUR_GOLD, COLOUR_NEUTRAL,
)

MONTH_SECONDS = 2592000  # 30 days


class Social(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ────────────────────────────────────────────────────────────────
    # Hype Keeper
    # ────────────────────────────────────────────────────────────────

    async def record_hype_vote(self, guild_id: int, user_id: int, ts: float):
        """Called by longgame cog when a vote is cast."""
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT vote_timestamps, total_votes FROM hype_keeper WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            cutoff = ts - MONTH_SECONDS
            if rows:
                timestamps = json.loads(rows[0]["vote_timestamps"])
                total = rows[0]["total_votes"]
            else:
                timestamps, total = [], 0

            timestamps.append(ts)
            timestamps = [t for t in timestamps if t >= cutoff]  # rolling 30-day window
            total += 1

            await db.execute("""
                INSERT INTO hype_keeper VALUES (?,?,?,?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    vote_timestamps=excluded.vote_timestamps,
                    total_votes=excluded.total_votes
            """, (guild_id, user_id, json.dumps(timestamps), total))
            await db.commit()

    hype = app_commands.Group(name="hype", description="Hype Keeper commands.")

    @hype.command(name="leaderboard", description="View the Hype Keeper monthly vote leaderboard.")
    async def hype_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "hype_keeper"):
            return await interaction.response.send_message(embed=not_enabled_embed("Hype Keeper"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, vote_timestamps, total_votes FROM hype_keeper WHERE guild_id=?", (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)

        now = now_ts()
        cutoff = now - MONTH_SECONDS
        ranked = []
        for r in rows:
            ts_list = json.loads(r["vote_timestamps"])
            monthly = sum(1 for t in ts_list if t >= cutoff)
            ranked.append((r["user_id"], monthly, r["total_votes"]))
        ranked.sort(key=lambda x: -x[1])

        lb_rows = []
        for i, (uid, monthly, total) in enumerate(ranked[:10], 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            lb_rows.append((i, name, f"🔊 {monthly} votes this month · {total} all-time"))
        await interaction.response.send_message(embed=leaderboard_embed("🔊 Hype Keeper", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Loyal Opposition
    # ────────────────────────────────────────────────────────────────

    async def record_loyal_opposition(self, guild_id: int, user_id: int, round_id: int, is_contrarian: bool):
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM loyal_opposition WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            if rows:
                await db.execute("""
                    UPDATE loyal_opposition SET
                        contrarian_count = contrarian_count + ?,
                        rounds_participated = rounds_participated + 1
                    WHERE guild_id=? AND user_id=?
                """, (int(is_contrarian), guild_id, user_id))
            else:
                await db.execute(
                    "INSERT INTO loyal_opposition VALUES (?,?,?,?)",
                    (guild_id, user_id, int(is_contrarian), 1)
                )
            await db.commit()

    opposition = app_commands.Group(name="opposition", description="Loyal Opposition leaderboard.")

    @opposition.command(name="leaderboard", description="View the Loyal Opposition leaderboard.")
    async def opposition_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "loyal_opposition"):
            return await interaction.response.send_message(embed=not_enabled_embed("Loyal Opposition"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT user_id, contrarian_count, rounds_participated
                   FROM loyal_opposition WHERE guild_id=? AND rounds_participated >= 3
                   ORDER BY contrarian_count DESC LIMIT 10""",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(
                embed=warning_embed("No Data", "Not enough data yet (min 3 rounds participated)."), ephemeral=True
            )
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            pct = int(r["contrarian_count"] / r["rounds_participated"] * 100)
            lb_rows.append((i, name, f"🎭 {r['contrarian_count']} contrarian votes ({pct}% of rounds)"))
        await interaction.response.send_message(
            embed=leaderboard_embed("🎭 Loyal Opposition", lb_rows, colour=COLOUR_NEUTRAL)
        )

    # ────────────────────────────────────────────────────────────────
    # Streak Breaker (Hall of Shame)
    # ────────────────────────────────────────────────────────────────

    shame = app_commands.Group(name="shame", description="Streak Breaker hall of shame.")

    @shame.command(name="board", description="View the Streak Breaker hall of shame.")
    async def shame_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "streak_breaker"):
            return await interaction.response.send_message(embed=not_enabled_embed("Streak Breaker"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT user_id, broken_streak, broken_at FROM streak_breaker
                   WHERE guild_id=? ORDER BY broken_streak DESC LIMIT 10""",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(
                embed=warning_embed("No Broken Streaks", "Nobody has broken a streak yet. Impressive!"), ephemeral=True
            )
        embed = base_embed(
            "😢 Streak Breaker — Hall of Shame",
            "A place of commiseration for streaks that didn't make it. 🪦",
            colour=0x95A5A6,
        )
        for r in rows[:10]:
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            broken_dt = ts_to_dt(r["broken_at"]).strftime("%d %b %Y")
            embed.add_field(
                name=f"💔 {name}",
                value=f"Streak of **{r['broken_streak']} days** broke on {broken_dt}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Social(bot))
