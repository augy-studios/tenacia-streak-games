"""
Streaks cog — Rolling Streak, Momentum Board, Persistence Cup, The Faithful.
"""
import discord
import json
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from utils.db import get_db, now_ts, ts_to_dt
from utils.settings import is_enabled
from utils.embeds import (
    success_embed, warning_embed, not_enabled_embed, leaderboard_embed,
    base_embed, COLOUR_PRIMARY, COLOUR_GOLD, COLOUR_BRONZE,
)

ROLLING_WINDOW = 86400      # 24 hours in seconds
PERSISTENCE_WINDOW = 604800 # 7 days in seconds
PERSISTENCE_MIN_DAYS = 5
FAITHFUL_MIN_POSTS = 1      # at least 1 post per calendar month (UTC)


def _format_streak(n: int) -> str:
    return f"**{n}** day{'s' if n != 1 else ''}"


class Streaks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ────────────────────────────────────────────────────────────────
    # Rolling Streak
    # ────────────────────────────────────────────────────────────────

    streak = app_commands.Group(name="streak", description="Rolling Streak commands.")

    @streak.command(name="checkin", description="Check in to keep your rolling streak alive.")
    async def streak_checkin(self, interaction: discord.Interaction):
        gid, uid = interaction.guild_id, interaction.user.id
        if not await is_enabled(gid, "rolling_streak"):
            return await interaction.response.send_message(embed=not_enabled_embed("Rolling Streak"), ephemeral=True)

        now = now_ts()
        async with await get_db() as db:
            row = await db.execute_fetchall(
                "SELECT * FROM rolling_streak WHERE guild_id=? AND user_id=?", (gid, uid)
            )
            if row:
                r = row[0]
                last = r["last_checkin"]
                cur = r["current_streak"]
                best = r["best_streak"]
                total = r["total_checkins"]

                if last and (now - last) < ROLLING_WINDOW:
                    remaining = ROLLING_WINDOW - (now - last)
                    h, rem = divmod(int(remaining), 3600)
                    m = rem // 60
                    embed = warning_embed(
                        "Already Checked In",
                        f"You already checked in! Come back in **{h}h {m}m**.\n"
                        f"Current streak: {_format_streak(cur)}"
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                if last and (now - last) >= ROLLING_WINDOW * 2:
                    # Streak broken
                    if cur > 0:
                        await db.execute(
                            "INSERT INTO streak_breaker (guild_id, user_id, broken_streak, broken_at) VALUES (?,?,?,?)",
                            (gid, uid, cur, now)
                        )
                    cur = 1
                else:
                    cur += 1

                best = max(best, cur)
                await db.execute("""
                    UPDATE rolling_streak
                    SET last_checkin=?, current_streak=?, best_streak=?, total_checkins=total_checkins+1
                    WHERE guild_id=? AND user_id=?
                """, (now, cur, best, gid, uid))
            else:
                cur, best = 1, 1
                await db.execute(
                    "INSERT INTO rolling_streak VALUES (?,?,?,?,?,?)",
                    (gid, uid, now, cur, best, 1)
                )
            await db.commit()

        embed = success_embed(
            "Streak Check-In ✅",
            f"{interaction.user.mention} checked in!\n"
            f"🔥 Current streak: {_format_streak(cur)}\n"
            f"🏆 Personal best: {_format_streak(best)}"
        )
        await interaction.response.send_message(embed=embed)

        # Update momentum too
        await self._momentum_post(gid, uid, now)
        await self._faithful_post(gid, uid, now)

    @streak.command(name="profile", description="View your rolling streak profile.")
    async def streak_profile(self, interaction: discord.Interaction, member: discord.Member = None):
        gid = interaction.guild_id
        if not await is_enabled(gid, "rolling_streak"):
            return await interaction.response.send_message(embed=not_enabled_embed("Rolling Streak"), ephemeral=True)
        target = member or interaction.user
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM rolling_streak WHERE guild_id=? AND user_id=?", (gid, target.id)
            )
        if not rows:
            return await interaction.response.send_message(
                embed=warning_embed("No Data", f"{target.display_name} hasn't checked in yet."), ephemeral=True
            )
        r = rows[0]
        now = now_ts()
        last = r["last_checkin"]
        alive = last and (now - last) < ROLLING_WINDOW * 2
        status = "🟢 Active" if alive else "🔴 Broken"
        embed = base_embed(f"Streak Profile — {target.display_name}", colour=COLOUR_GOLD)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Current Streak", value=_format_streak(r["current_streak"]), inline=True)
        embed.add_field(name="All-Time Best", value=_format_streak(r["best_streak"]), inline=True)
        embed.add_field(name="Total Check-Ins", value=str(r["total_checkins"]), inline=True)
        await interaction.response.send_message(embed=embed)

    @streak.command(name="leaderboard", description="View the rolling streak leaderboard.")
    async def streak_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "rolling_streak"):
            return await interaction.response.send_message(embed=not_enabled_embed("Rolling Streak"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, current_streak, best_streak FROM rolling_streak WHERE guild_id=? ORDER BY current_streak DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No check-ins yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🔥 {r['current_streak']} days · Best: {r['best_streak']}"))
        embed = leaderboard_embed("🔥 Rolling Streak Leaderboard", lb_rows)
        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────────────
    # Momentum Board (internal helper + slash commands)
    # ────────────────────────────────────────────────────────────────

    async def _momentum_post(self, guild_id: int, user_id: int, ts: float):
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM momentum_board WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            if rows:
                r = rows[0]
                last = r["last_post_ts"]
                cur = r["current_streak"]
                best = r["best_streak"]
                if last is None:
                    cur, best = 1, 1
                elif (ts - last) < ROLLING_WINDOW:
                    pass  # same window, no change
                elif (ts - last) < ROLLING_WINDOW * 2:
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 1  # reset
                await db.execute("""
                    UPDATE momentum_board SET last_post_ts=?, current_streak=?, best_streak=?
                    WHERE guild_id=? AND user_id=?
                """, (ts, cur, best, guild_id, user_id))
            else:
                await db.execute(
                    "INSERT INTO momentum_board VALUES (?,?,?,?,?,?)",
                    (guild_id, user_id, ts, ts, 1, 1)
                )
            await db.commit()

    momentum = app_commands.Group(name="momentum", description="Momentum Board commands.")

    @momentum.command(name="leaderboard", description="View the momentum board.")
    async def momentum_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "momentum_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Momentum Board"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, current_streak, best_streak FROM momentum_board WHERE guild_id=? ORDER BY current_streak DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"📅 {r['current_streak']} days · Best: {r['best_streak']}"))
        await interaction.response.send_message(embed=leaderboard_embed("📅 Momentum Board", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Persistence Cup
    # ────────────────────────────────────────────────────────────────

    async def record_persistence_post(self, guild_id: int, user_id: int, ts: float):
        """Called from on_message; updates rolling 7-day window post log."""
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT post_timestamps, qualifying_weeks FROM persistence_cup WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            cutoff = ts - PERSISTENCE_WINDOW
            if rows:
                timestamps = json.loads(rows[0]["post_timestamps"])
                qw = rows[0]["qualifying_weeks"]
            else:
                timestamps, qw = [], 0

            # Only add if not already within 1 hour of an existing stamp (dedup)
            if not timestamps or (ts - timestamps[-1]) > 3600:
                timestamps.append(ts)

            # Trim old
            timestamps = [t for t in timestamps if t >= cutoff]

            # Count distinct days within window
            days_hit = len(set(ts_to_dt(t).date() for t in timestamps))
            if days_hit >= PERSISTENCE_MIN_DAYS:
                # Qualifying window — only count once per 7-day cycle
                window_key = int(ts // PERSISTENCE_WINDOW)
                marked = json.dumps(timestamps)
                # Use qualifying_weeks as a last-window-counted tracker (simple)
                if qw != window_key:
                    qw = window_key
                    await db.execute("""
                        INSERT INTO persistence_cup VALUES (?,?,?,?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                            post_timestamps=excluded.post_timestamps,
                            qualifying_weeks=excluded.qualifying_weeks
                    """, (guild_id, user_id, marked, qw))
                else:
                    await db.execute("""
                        INSERT INTO persistence_cup VALUES (?,?,?,?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                            post_timestamps=excluded.post_timestamps
                    """, (guild_id, user_id, marked, qw))
            else:
                await db.execute("""
                    INSERT INTO persistence_cup VALUES (?,?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        post_timestamps=excluded.post_timestamps
                """, (guild_id, user_id, json.dumps(timestamps), qw))
            await db.commit()

    persistence = app_commands.Group(name="persistence", description="Persistence Cup commands.")

    @persistence.command(name="leaderboard", description="View the Persistence Cup leaderboard.")
    async def persistence_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "persistence_cup"):
            return await interaction.response.send_message(embed=not_enabled_embed("Persistence Cup"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT user_id, post_timestamps FROM persistence_cup WHERE guild_id=?""", (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)

        now = now_ts()
        cutoff = now - PERSISTENCE_WINDOW
        ranked = []
        for r in rows:
            ts_list = json.loads(r["post_timestamps"])
            recent = [t for t in ts_list if t >= cutoff]
            days_hit = len(set(ts_to_dt(t).date() for t in recent))
            ranked.append((r["user_id"], days_hit))
        ranked.sort(key=lambda x: -x[1])

        lb_rows = []
        for i, (uid, days) in enumerate(ranked[:10], 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            bar = "▓" * days + "░" * (7 - days)
            lb_rows.append((i, name, f"{bar} {days}/7 days this week"))
        await interaction.response.send_message(embed=leaderboard_embed("🏆 Persistence Cup", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # The Faithful
    # ────────────────────────────────────────────────────────────────

    async def _faithful_post(self, guild_id: int, user_id: int, ts: float):
        month_key = ts_to_dt(ts).strftime("%Y-%m")
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT months_active, active_months FROM the_faithful WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            if rows:
                months = json.loads(rows[0]["active_months"])
                count = rows[0]["months_active"]
                if month_key not in months:
                    months.append(month_key)
                    count += 1
                    await db.execute("""
                        UPDATE the_faithful SET months_active=?, active_months=?
                        WHERE guild_id=? AND user_id=?
                    """, (count, json.dumps(months), guild_id, user_id))
            else:
                await db.execute(
                    "INSERT INTO the_faithful VALUES (?,?,?,?)",
                    (guild_id, user_id, 1, json.dumps([month_key]))
                )
            await db.commit()

    faithful = app_commands.Group(name="faithful", description="The Faithful hall-of-fame commands.")

    @faithful.command(name="leaderboard", description="View The Faithful hall of fame.")
    async def faithful_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "the_faithful"):
            return await interaction.response.send_message(embed=not_enabled_embed("The Faithful"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, months_active FROM the_faithful WHERE guild_id=? ORDER BY months_active DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"📅 {r['months_active']} active month(s)"))
        await interaction.response.send_message(embed=leaderboard_embed("⛪ The Faithful", lb_rows, colour=COLOUR_BRONZE))

    # ────────────────────────────────────────────────────────────────
    # on_message hook — record persistence and faithful posts
    # ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid, uid = message.guild.id, message.author.id
        ts = message.created_at.timestamp()
        if await is_enabled(gid, "persistence_cup"):
            await self.record_persistence_post(gid, uid, ts)
        if await is_enabled(gid, "the_faithful"):
            await self._faithful_post(gid, uid, ts)
        if await is_enabled(gid, "momentum_board"):
            await self._momentum_post(gid, uid, ts)


async def setup(bot: commands.Bot):
    await bot.add_cog(Streaks(bot))
