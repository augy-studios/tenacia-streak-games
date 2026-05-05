"""
Leaderboards cog — aggregated views:
Weekly Board, Monthly Board, All-Time Legacy, Streak Board, Voter Board, Underdog Board.
"""
import discord
import json
from discord import app_commands
from discord.ext import commands
from utils.db import get_db, now_ts
from utils.settings import is_enabled
from utils.embeds import (
    warning_embed, not_enabled_embed, leaderboard_embed,
    base_embed, COLOUR_GOLD, COLOUR_PRIMARY, COLOUR_BRONZE,
)

WEEK_SECS  = 604800
MONTH_SECS = 2592000


class Leaderboards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    boards = app_commands.Group(name="boards", description="View aggregated leaderboards.")

    # ── Weekly Board ──────────────────────────────────────────────────

    @boards.command(name="weekly", description="Rolling 7-day leaderboard across all games.")
    async def weekly_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "weekly_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Weekly Leaderboard"), ephemeral=True)

        now = now_ts()
        cutoff = now - WEEK_SECS
        scores: dict[int, int] = {}

        async with await get_db() as db:
            # Prompt responses this week
            rows = await db.execute_fetchall(
                """SELECT pr.user_id, COUNT(*) as c FROM prompt_responses pr
                   JOIN daily_prompts dp ON pr.prompt_id=dp.id
                   WHERE pr.guild_id=? AND dp.posted_at>=?
                   GROUP BY pr.user_id""",
                (gid, cutoff)
            )
            for r in rows:
                scores[r["user_id"]] = scores.get(r["user_id"], 0) + r["c"]

            # Streak check-ins this week
            rows2 = await db.execute_fetchall(
                "SELECT user_id FROM rolling_streak WHERE guild_id=? AND last_checkin>=?",
                (gid, cutoff)
            )
            for r in rows2:
                scores[r["user_id"]] = scores.get(r["user_id"], 0) + 1

            # Round submissions this week
            rows3 = await db.execute_fetchall(
                """SELECT rs.user_id, COUNT(*) as c FROM round_submissions rs
                   JOIN creative_rounds cr ON rs.round_id=cr.id
                   WHERE rs.guild_id=? AND cr.started_at>=?
                   GROUP BY rs.user_id""",
                (gid, cutoff)
            )
            for r in rows3:
                scores[r["user_id"]] = scores.get(r["user_id"], 0) + r["c"]

            # Votes this week
            rows4 = await db.execute_fetchall(
                """SELECT voter_id, COUNT(*) as c FROM round_votes
                   WHERE guild_id=? AND voted_at>=?
                   GROUP BY voter_id""",
                (gid, cutoff)
            )
            for r in rows4:
                scores[r["voter_id"]] = scores.get(r["voter_id"], 0) + r["c"]

        if not scores:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No activity this week."), ephemeral=True)

        ranked = sorted(scores.items(), key=lambda x: -x[1])[:10]
        lb_rows = []
        for i, (uid, score) in enumerate(ranked, 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            lb_rows.append((i, name, f"⚡ {score} activity point(s) this week"))
        await interaction.response.send_message(
            embed=leaderboard_embed("📅 Weekly Board (Rolling 7 Days)", lb_rows, colour=COLOUR_PRIMARY)
        )

    # ── Monthly Board ─────────────────────────────────────────────────

    @boards.command(name="monthly", description="Rolling 30-day leaderboard.")
    async def monthly_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "monthly_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Monthly Leaderboard"), ephemeral=True)

        now = now_ts()
        cutoff = now - MONTH_SECS
        scores: dict[int, int] = {}

        async with await get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT pr.user_id, COUNT(*) as c FROM prompt_responses pr
                   JOIN daily_prompts dp ON pr.prompt_id=dp.id
                   WHERE pr.guild_id=? AND dp.posted_at>=? GROUP BY pr.user_id""",
                (gid, cutoff)
            )
            for r in rows:
                scores[r["user_id"]] = scores.get(r["user_id"], 0) + r["c"] * 2

            rows2 = await db.execute_fetchall(
                """SELECT rs.user_id, COUNT(*) as c FROM round_submissions rs
                   JOIN creative_rounds cr ON rs.round_id=cr.id
                   WHERE rs.guild_id=? AND cr.started_at>=? GROUP BY rs.user_id""",
                (gid, cutoff)
            )
            for r in rows2:
                scores[r["user_id"]] = scores.get(r["user_id"], 0) + r["c"] * 3

            rows3 = await db.execute_fetchall(
                """SELECT voter_id, COUNT(*) as c FROM round_votes
                   WHERE guild_id=? AND voted_at>=? GROUP BY voter_id""",
                (gid, cutoff)
            )
            for r in rows3:
                scores[r["voter_id"]] = scores.get(r["voter_id"], 0) + r["c"]

        if not scores:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No activity this month."), ephemeral=True)

        ranked = sorted(scores.items(), key=lambda x: -x[1])[:10]
        lb_rows = []
        for i, (uid, score) in enumerate(ranked, 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            lb_rows.append((i, name, f"📆 {score} points this month"))
        await interaction.response.send_message(
            embed=leaderboard_embed("📆 Monthly Board (Rolling 30 Days)", lb_rows, colour=COLOUR_GOLD)
        )

    # ── All-Time Legacy Board ─────────────────────────────────────────

    @boards.command(name="alltime", description="All-time Legacy Points leaderboard.")
    async def alltime_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "alltime_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("All-Time Legacy Board"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, total_points, wins, submissions FROM legacy_points WHERE guild_id=? ORDER BY total_points DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"📜 {r['total_points']} pts · 🏆 {r['wins']}W · ✏️ {r['submissions']} subs"))
        await interaction.response.send_message(
            embed=leaderboard_embed("👑 All-Time Legacy Board", lb_rows)
        )

    # ── Streak Board ──────────────────────────────────────────────────

    @boards.command(name="streaks", description="Current and all-time personal streak records.")
    async def streak_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "streak_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Streak Board"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, current_streak, best_streak FROM rolling_streak WHERE guild_id=? ORDER BY current_streak DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No streaks yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🔥 {r['current_streak']} now · 🏆 {r['best_streak']} all-time"))
        await interaction.response.send_message(
            embed=leaderboard_embed("🔥 Streak Board", lb_rows, colour=0xFF6B35)
        )

    # ── Voter Board ───────────────────────────────────────────────────

    @boards.command(name="voters", description="Leaderboard for the most engaged voters.")
    async def voter_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "voter_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Voter Board"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, total_votes FROM hype_keeper WHERE guild_id=? ORDER BY total_votes DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No votes cast yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🗳️ {r['total_votes']} total votes cast"))
        await interaction.response.send_message(
            embed=leaderboard_embed("🗳️ Voter Board", lb_rows, colour=COLOUR_PRIMARY)
        )

    # ── Underdog Board ────────────────────────────────────────────────

    @boards.command(name="underdogs", description="Wins by members in the bottom half of Legacy Points.")
    async def underdog_board(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "underdog_board"):
            return await interaction.response.send_message(embed=not_enabled_embed("Underdog Board"), ephemeral=True)
        async with await get_db() as db:
            all_rows = await db.execute_fetchall(
                "SELECT user_id, total_points, wins FROM legacy_points WHERE guild_id=? ORDER BY total_points ASC",
                (gid,)
            )
        if not all_rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        half = max(1, len(all_rows) // 2)
        bottom_half = sorted(all_rows[:half], key=lambda r: -r["wins"])
        lb_rows = []
        for i, r in enumerate(bottom_half[:10], 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"⚡ {r['wins']} win(s) with only {r['total_points']} pts"))
        await interaction.response.send_message(
            embed=leaderboard_embed("⚡ Underdog Board", lb_rows, colour=COLOUR_BRONZE)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboards(bot))
