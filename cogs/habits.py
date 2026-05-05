"""
Habits cog — Daily Prompt Responder, Submission Soldier,
              Voter Vigilance, The Completionist.
"""
import discord
import aiohttp
import json
from discord import app_commands
from discord.ext import commands
from utils.db import get_db, now_ts, ts_to_dt
from utils.settings import is_enabled, get_channel
from utils.embeds import (
    success_embed, warning_embed, not_enabled_embed,
    leaderboard_embed, base_embed, COLOUR_PRIMARY, COLOUR_GOLD,
)

COMPLETIONIST_WINDOW = 2592000  # 30 days


# ── Open-source prompt APIs ──────────────────────────────────────────────────
PROMPT_APIS = [
    "https://api.quotable.io/random?tags=inspirational|wisdom|life",
    "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en",
]

async def fetch_prompt() -> str:
    """Fetch a creative prompt/quote from a free public API."""
    async with aiohttp.ClientSession() as session:
        # Try quotable.io first
        try:
            async with session.get("https://api.quotable.io/random", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    return f'"{data["content"]}" — {data["author"]}\n\n*What does this quote mean to you?*'
        except Exception:
            pass
        # Fallback: useless facts as conversation starters
        try:
            async with session.get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    return f"💡 **Did you know?** {data['text']}\n\n*Share your thoughts or a related experience!*"
        except Exception:
            pass
    return "What's something you've learned recently that surprised you? Share it here! 🌟"


class Habits(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ────────────────────────────────────────────────────────────────
    # Daily Prompt Responder
    # ────────────────────────────────────────────────────────────────

    prompt = app_commands.Group(name="prompt", description="Daily Prompt Responder commands.")

    @prompt.command(name="post", description="Post today's daily prompt (admin or auto-scheduled).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def prompt_post(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "daily_prompt"):
            return await interaction.response.send_message(embed=not_enabled_embed("Daily Prompt Responder"), ephemeral=True)

        await interaction.response.defer()
        prompt_text = await fetch_prompt()
        now = now_ts()

        async with await get_db() as db:
            cursor = await db.execute(
                "INSERT INTO daily_prompts (guild_id, prompt_text, posted_at) VALUES (?,?,?)",
                (gid, prompt_text, now)
            )
            prompt_id = cursor.lastrowid
            await db.commit()

        channel_id = await get_channel(gid, "daily_prompt")
        channel = (
            self.bot.get_channel(channel_id)
            if channel_id else interaction.channel
        )

        embed = base_embed(
            "📝 Daily Prompt",
            f"{prompt_text}\n\n"
            f"Use `/prompt respond` to earn your point!\n"
            f"*Prompt ID: `{prompt_id}`*",
            colour=COLOUR_PRIMARY,
        )
        msg = await channel.send(embed=embed)

        async with await get_db() as db:
            await db.execute("UPDATE daily_prompts SET message_id=? WHERE id=?", (msg.id, prompt_id))
            await db.commit()

        if channel != interaction.channel:
            await interaction.followup.send(embed=success_embed("Prompt Posted", f"Today's prompt was posted in {channel.mention}."), ephemeral=True)

    @prompt.command(name="respond", description="Respond to the latest daily prompt to earn a point.")
    @app_commands.describe(response="Your response to today's prompt")
    async def prompt_respond(self, interaction: discord.Interaction, response: str):
        gid, uid = interaction.guild_id, interaction.user.id
        if not await is_enabled(gid, "daily_prompt"):
            return await interaction.response.send_message(embed=not_enabled_embed("Daily Prompt Responder"), ephemeral=True)

        now = now_ts()
        cutoff = now - 86400  # last 24 hours

        async with await get_db() as db:
            prompts = await db.execute_fetchall(
                "SELECT id FROM daily_prompts WHERE guild_id=? AND posted_at>=? ORDER BY posted_at DESC LIMIT 1",
                (gid, cutoff)
            )
            if not prompts:
                return await interaction.response.send_message(
                    embed=warning_embed("No Active Prompt", "There's no active prompt right now. Wait for the next one!"),
                    ephemeral=True
                )
            prompt_id = prompts[0]["id"]
            existing = await db.execute_fetchall(
                "SELECT 1 FROM prompt_responses WHERE guild_id=? AND user_id=? AND prompt_id=?",
                (gid, uid, prompt_id)
            )
            if existing:
                return await interaction.response.send_message(
                    embed=warning_embed("Already Responded", "You already responded to today's prompt!"),
                    ephemeral=True
                )
            await db.execute(
                "INSERT INTO prompt_responses VALUES (?,?,?,?)",
                (gid, uid, prompt_id, now)
            )
            total = await db.execute_fetchall(
                "SELECT COUNT(*) as c FROM prompt_responses WHERE guild_id=? AND user_id=?",
                (gid, uid)
            )
            await db.commit()

        total_count = total[0]["c"]
        embed = success_embed(
            "Prompt Responded ✅",
            f"{interaction.user.mention} responded to today's prompt!\n"
            f"📝 Total prompts responded: **{total_count}**\n\n"
            f"*Your response:* {response[:200]}"
        )
        await interaction.response.send_message(embed=embed)

    @prompt.command(name="leaderboard", description="View the Daily Prompt Responder leaderboard.")
    async def prompt_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "daily_prompt"):
            return await interaction.response.send_message(embed=not_enabled_embed("Daily Prompt Responder"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                """SELECT user_id, COUNT(*) as cnt FROM prompt_responses
                   WHERE guild_id=? GROUP BY user_id ORDER BY cnt DESC LIMIT 10""",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No responses yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"📝 {r['cnt']} prompt(s) responded"))
        await interaction.response.send_message(embed=leaderboard_embed("📝 Daily Prompt Leaderboard", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Submission Soldier
    # ────────────────────────────────────────────────────────────────

    soldier = app_commands.Group(name="soldier", description="Submission Soldier commands.")

    async def record_submission(self, guild_id: int, user_id: int, round_id: int):
        """Called when a member submits to a creative round."""
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM submission_soldier WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            if rows:
                r = rows[0]
                last = r["last_round_id"]
                cur = r["current_streak"]
                best = r["best_streak"]
                # Check if last round was immediately prior (consecutive)
                # We trust round IDs to be sequential
                if last is None or round_id == last + 1:
                    cur += 1
                elif round_id == last:
                    return  # duplicate, skip
                else:
                    cur = 1  # gap — reset
                best = max(best, cur)
                await db.execute("""
                    UPDATE submission_soldier SET current_streak=?, best_streak=?, last_round_id=?
                    WHERE guild_id=? AND user_id=?
                """, (cur, best, round_id, guild_id, user_id))
            else:
                await db.execute(
                    "INSERT INTO submission_soldier VALUES (?,?,?,?,?)",
                    (guild_id, user_id, 1, 1, round_id)
                )
            await db.commit()

    @soldier.command(name="leaderboard", description="View the Submission Soldier leaderboard.")
    async def soldier_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "submission_soldier"):
            return await interaction.response.send_message(embed=not_enabled_embed("Submission Soldier"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, current_streak, best_streak FROM submission_soldier WHERE guild_id=? ORDER BY current_streak DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🪖 {r['current_streak']} rounds · Best: {r['best_streak']}"))
        await interaction.response.send_message(embed=leaderboard_embed("🪖 Submission Soldier", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Voter Vigilance
    # ────────────────────────────────────────────────────────────────

    vigilance = app_commands.Group(name="vigilance", description="Voter Vigilance commands.")

    async def record_vote_vigilance(self, guild_id: int, user_id: int, round_id: int):
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM voter_vigilance WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            if rows:
                if rows[0]["last_voted_round"] == round_id:
                    return
                await db.execute("""
                    UPDATE voter_vigilance SET voting_windows=voting_windows+1, last_voted_round=?
                    WHERE guild_id=? AND user_id=?
                """, (round_id, guild_id, user_id))
            else:
                await db.execute(
                    "INSERT INTO voter_vigilance VALUES (?,?,?,?)",
                    (guild_id, user_id, 1, round_id)
                )
            await db.commit()

    @vigilance.command(name="leaderboard", description="View the Voter Vigilance leaderboard.")
    async def vigilance_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "voter_vigilance"):
            return await interaction.response.send_message(embed=not_enabled_embed("Voter Vigilance"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, voting_windows FROM voter_vigilance WHERE guild_id=? ORDER BY voting_windows DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🗳️ {r['voting_windows']} voting windows participated"))
        await interaction.response.send_message(embed=leaderboard_embed("🗳️ Voter Vigilance", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # The Completionist
    # ────────────────────────────────────────────────────────────────

    completionist = app_commands.Group(name="completionist", description="The Completionist hall of fame.")

    async def check_completionist(self, guild_id: int, user_id: int, round_id: int):
        """Check if user both submitted and voted in this round; award if so."""
        async with await get_db() as db:
            submitted = await db.execute_fetchall(
                "SELECT 1 FROM round_submissions WHERE guild_id=? AND user_id=? AND round_id=?",
                (guild_id, user_id, round_id)
            )
            voted = await db.execute_fetchall(
                "SELECT 1 FROM round_votes WHERE guild_id=? AND voter_id=? AND round_id=?",
                (guild_id, user_id, round_id)
            )
            if submitted and voted:
                now = now_ts()
                rows = await db.execute_fetchall(
                    "SELECT achievements FROM completionist WHERE guild_id=? AND user_id=?",
                    (guild_id, user_id)
                )
                if rows:
                    await db.execute("""
                        UPDATE completionist SET achievements=achievements+1, last_achieved=?
                        WHERE guild_id=? AND user_id=?
                    """, (now, guild_id, user_id))
                else:
                    await db.execute(
                        "INSERT INTO completionist VALUES (?,?,?,?)",
                        (guild_id, user_id, 1, now)
                    )
                await db.commit()
                return True
        return False

    @completionist.command(name="leaderboard", description="View The Completionist hall of fame.")
    async def completionist_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "completionist"):
            return await interaction.response.send_message(embed=not_enabled_embed("The Completionist"), ephemeral=True)
        async with await get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, achievements FROM completionist WHERE guild_id=? ORDER BY achievements DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No completionist achievements yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"⭐ {r['achievements']} complete round(s)"))
        await interaction.response.send_message(embed=leaderboard_embed("⭐ The Completionist Hall of Fame", lb_rows, colour=COLOUR_GOLD))


async def setup(bot: commands.Bot):
    await bot.add_cog(Habits(bot))
