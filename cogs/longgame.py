"""
Long Game cog — Legacy Points, Comeback Counter, Underdog Rising, The Grind.
Also manages creative rounds (open/close/submit/vote).
"""
import discord
from discord import app_commands
from discord.ext import commands
from utils.db import get_db, now_ts
from utils.settings import is_enabled, get_channel
from utils.embeds import (
    success_embed, warning_embed, danger_embed, not_enabled_embed,
    leaderboard_embed, base_embed, COLOUR_GOLD, COLOUR_PRIMARY, COLOUR_BRONZE,
)

COMEBACK_ABSENCE = 1209600  # 14 days in seconds


def _legacy_points_from(r) -> int:
    return r["submissions"] + r["votes_received"] + r["wins"] * 5


class LongGame(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ────────────────────────────────────────────────────────────────
    # Creative Rounds Management
    # ────────────────────────────────────────────────────────────────

    round_cmd = app_commands.Group(name="round", description="Manage creative rounds.")

    @round_cmd.command(name="open", description="Open a new creative round.")
    @app_commands.describe(name="Name or theme for this round")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def round_open(self, interaction: discord.Interaction, name: str):
        gid = interaction.guild_id
        now = now_ts()
        async with get_db() as db:
            open_rounds = await db.execute_fetchall(
                "SELECT id FROM creative_rounds WHERE guild_id=? AND is_open=1", (gid,)
            )
            if open_rounds:
                return await interaction.response.send_message(
                    embed=warning_embed("Round Already Open", "Close the current round before opening a new one."),
                    ephemeral=True
                )
            cursor = await db.execute(
                "INSERT INTO creative_rounds (guild_id, round_name, started_at) VALUES (?,?,?)",
                (gid, name, now)
            )
            round_id = cursor.lastrowid
            await db.commit()

        embed = success_embed(
            f"🎨 Round Opened: {name}",
            f"Round **#{round_id}** is now open!\n"
            f"Members can submit with `/round submit` and vote with `/round vote`."
        )
        channel_id = await get_channel(gid, "legacy_points")
        channel = self.bot.get_channel(channel_id) if channel_id else interaction.channel
        await channel.send(embed=embed)
        if channel != interaction.channel:
            await interaction.response.send_message(embed=success_embed("Round Opened", f"Posted in {channel.mention}."), ephemeral=True)
        else:
            await interaction.response.send_message("✅", ephemeral=True, delete_after=1)

    @round_cmd.command(name="close", description="Close the current creative round and tally results.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def round_close(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        now = now_ts()
        async with get_db() as db:
            open_rounds = await db.execute_fetchall(
                "SELECT * FROM creative_rounds WHERE guild_id=? AND is_open=1", (gid,)
            )
            if not open_rounds:
                return await interaction.response.send_message(
                    embed=warning_embed("No Open Round", "There is no open round to close."), ephemeral=True
                )
            rnd = open_rounds[0]
            round_id = rnd["id"]

            # Tally votes
            votes = await db.execute_fetchall(
                "SELECT voted_for_id, COUNT(*) as vc FROM round_votes WHERE guild_id=? AND round_id=? GROUP BY voted_for_id ORDER BY vc DESC",
                (gid, round_id)
            )
            submissions = await db.execute_fetchall(
                "SELECT user_id FROM round_submissions WHERE guild_id=? AND round_id=?", (gid, round_id)
            )
            voters = await db.execute_fetchall(
                "SELECT voter_id FROM round_votes WHERE guild_id=? AND round_id=?", (gid, round_id)
            )

            # Award Legacy Points
            for sub in submissions:
                uid = sub["user_id"]
                await self._add_legacy(db, gid, uid, submissions_delta=1, round_id=round_id)

            winner_id = None
            if votes:
                winner_id = votes[0]["voted_for_id"]
                winner_votes = votes[0]["vc"]
                await self._add_legacy(db, gid, winner_id, wins_delta=1)
                for v in votes:
                    await self._add_legacy(db, gid, v["voted_for_id"], votes_received_delta=v["vc"])

            for voter in voters:
                vid = voter["voter_id"]
                await self._add_legacy(db, gid, vid)

            await db.execute("UPDATE creative_rounds SET is_open=0, ended_at=? WHERE id=?", (now, round_id))
            await db.commit()

        # Compose close message
        embed = base_embed(f"🏁 Round #{round_id} Closed — {rnd['round_name']}", colour=COLOUR_GOLD)
        embed.add_field(name="Submissions", value=str(len(submissions)), inline=True)
        embed.add_field(name="Votes Cast", value=str(len(voters)), inline=True)
        if winner_id:
            member = interaction.guild.get_member(winner_id)
            winner_name = member.mention if member else f"<@{winner_id}>"
            embed.add_field(name="🥇 Winner", value=f"{winner_name} with {winner_votes} vote(s)!", inline=False)

        channel_id = await get_channel(gid, "legacy_points")
        channel = self.bot.get_channel(channel_id) if channel_id else interaction.channel
        await channel.send(embed=embed)

        # Check Loyal Opposition, Completionist for all participants
        habits_cog = self.bot.cogs.get("Habits")
        social_cog = self.bot.cogs.get("Social")
        for sub in submissions:
            if habits_cog:
                await habits_cog.record_submission(gid, sub["user_id"], round_id)
                await habits_cog.check_completionist(gid, sub["user_id"], round_id)
        for voter in voters:
            if habits_cog:
                await habits_cog.record_vote_vigilance(gid, voter["voter_id"], round_id)
                await habits_cog.check_completionist(gid, voter["voter_id"], round_id)
            if social_cog and winner_id:
                # Loyal opposition: voter who picked non-winner
                vote_row = await self._get_vote(gid, round_id, voter["voter_id"])
                if vote_row and vote_row["voted_for_id"] != winner_id:
                    await social_cog.record_loyal_opposition(gid, voter["voter_id"], round_id, True)
                else:
                    await social_cog.record_loyal_opposition(gid, voter["voter_id"], round_id, False)

        if channel != interaction.channel:
            await interaction.response.send_message(embed=success_embed("Round Closed", f"Results posted in {channel.mention}."), ephemeral=True)
        else:
            await interaction.response.send_message("✅", ephemeral=True, delete_after=1)

    async def _get_vote(self, gid, round_id, voter_id):
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT voted_for_id FROM round_votes WHERE guild_id=? AND round_id=? AND voter_id=?",
                (gid, round_id, voter_id)
            )
        return rows[0] if rows else None

    @round_cmd.command(name="submit", description="Submit an entry to the current creative round.")
    @app_commands.describe(content="Your submission (text, link, or description)")
    async def round_submit(self, interaction: discord.Interaction, content: str):
        gid, uid = interaction.guild_id, interaction.user.id
        now = now_ts()
        async with get_db() as db:
            open_rounds = await db.execute_fetchall(
                "SELECT id FROM creative_rounds WHERE guild_id=? AND is_open=1", (gid,)
            )
            if not open_rounds:
                return await interaction.response.send_message(
                    embed=warning_embed("No Open Round", "There's no open round right now."), ephemeral=True
                )
            round_id = open_rounds[0]["id"]
            existing = await db.execute_fetchall(
                "SELECT 1 FROM round_submissions WHERE round_id=? AND guild_id=? AND user_id=?",
                (round_id, gid, uid)
            )
            if existing:
                return await interaction.response.send_message(
                    embed=warning_embed("Already Submitted", "You already submitted to this round."), ephemeral=True
                )

            # Comeback check
            comeback_row = await db.execute_fetchall(
                "SELECT last_submit_ts, comebacks FROM comeback_counter WHERE guild_id=? AND user_id=?",
                (gid, uid)
            )
            is_comeback = False
            if comeback_row and comeback_row[0]["last_submit_ts"]:
                absence = now - comeback_row[0]["last_submit_ts"]
                if absence >= COMEBACK_ABSENCE:
                    is_comeback = True
                    new_comebacks = comeback_row[0]["comebacks"] + 1
                    await db.execute("""
                        UPDATE comeback_counter SET comebacks=?, comeback_points=comeback_points+1, last_submit_ts=?
                        WHERE guild_id=? AND user_id=?
                    """, (new_comebacks, now, gid, uid))
                else:
                    await db.execute("UPDATE comeback_counter SET last_submit_ts=? WHERE guild_id=? AND user_id=?", (now, gid, uid))
            else:
                await db.execute(
                    "INSERT INTO comeback_counter VALUES (?,?,?,?,?) ON CONFLICT(guild_id, user_id) DO UPDATE SET last_submit_ts=excluded.last_submit_ts",
                    (gid, uid, 0, 0, now)
                )

            await db.execute(
                "INSERT INTO round_submissions VALUES (?,?,?,?)",
                (round_id, gid, uid, now)
            )

            # Update The Grind (via legacy_points submissions)
            await self._add_legacy(db, gid, uid, submissions_delta=0)  # will be counted on round close

            await db.commit()

        msg = f"{interaction.user.mention} submitted to round **#{round_id}**!"
        if is_comeback:
            msg += "\n\n🎉 **Comeback!** They were absent for 14+ days — welcome back!"

        embed = success_embed("Submission Received ✅", msg)
        embed.add_field(name="Submission", value=content[:500], inline=False)
        await interaction.response.send_message(embed=embed)

    @round_cmd.command(name="vote", description="Vote for a submission in the current round.")
    @app_commands.describe(member="The member you're voting for")
    async def round_vote(self, interaction: discord.Interaction, member: discord.Member):
        gid, uid = interaction.guild_id, interaction.user.id
        if member.id == uid:
            return await interaction.response.send_message(
                embed=danger_embed("Invalid Vote", "You can't vote for yourself."), ephemeral=True
            )
        now = now_ts()
        async with get_db() as db:
            open_rounds = await db.execute_fetchall(
                "SELECT id FROM creative_rounds WHERE guild_id=? AND is_open=1", (gid,)
            )
            if not open_rounds:
                return await interaction.response.send_message(
                    embed=warning_embed("No Open Round", "There's no open round right now."), ephemeral=True
                )
            round_id = open_rounds[0]["id"]

            submitted = await db.execute_fetchall(
                "SELECT 1 FROM round_submissions WHERE round_id=? AND guild_id=? AND user_id=?",
                (round_id, gid, member.id)
            )
            if not submitted:
                return await interaction.response.send_message(
                    embed=warning_embed("Not Submitted", f"{member.display_name} hasn't submitted to this round."), ephemeral=True
                )

            existing_vote = await db.execute_fetchall(
                "SELECT 1 FROM round_votes WHERE round_id=? AND guild_id=? AND voter_id=?",
                (round_id, gid, uid)
            )
            if existing_vote:
                return await interaction.response.send_message(
                    embed=warning_embed("Already Voted", "You already voted in this round."), ephemeral=True
                )

            await db.execute(
                "INSERT INTO round_votes VALUES (?,?,?,?,?)",
                (round_id, gid, uid, member.id, now)
            )
            # Hype Keeper
            social_cog = self.bot.cogs.get("Social")
            if social_cog:
                await social_cog.record_hype_vote(gid, uid, now)

            await db.commit()

        embed = success_embed("Vote Cast ✅", f"{interaction.user.mention} voted for **{member.display_name}** in round #{round_id}!")
        await interaction.response.send_message(embed=embed)

    @round_cmd.command(name="status", description="View the current round status.")
    async def round_status(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM creative_rounds WHERE guild_id=? AND is_open=1", (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Open Round", "No round is currently open."), ephemeral=True)
        r = rows[0]
        async with get_db() as db:
            subs = await db.execute_fetchall(
                "SELECT user_id FROM round_submissions WHERE guild_id=? AND round_id=?", (gid, r["id"])
            )
            votes = await db.execute_fetchall(
                "SELECT COUNT(*) as c FROM round_votes WHERE guild_id=? AND round_id=?", (gid, r["id"])
            )
        embed = base_embed(f"🎨 Round #{r['id']} — {r['round_name']}", colour=COLOUR_PRIMARY)
        embed.add_field(name="Status", value="🟢 Open", inline=True)
        embed.add_field(name="Submissions", value=str(len(subs)), inline=True)
        embed.add_field(name="Votes Cast", value=str(votes[0]["c"]), inline=True)
        sub_names = []
        for s in subs:
            mem = interaction.guild.get_member(s["user_id"])
            sub_names.append(mem.display_name if mem else f"User {s['user_id']}")
        if sub_names:
            embed.add_field(name="Submitted", value=", ".join(sub_names), inline=False)
        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────────────
    # Legacy Points (internal helper)
    # ────────────────────────────────────────────────────────────────

    async def _add_legacy(
        self, db,
        guild_id: int, user_id: int,
        submissions_delta: int = 0,
        votes_received_delta: int = 0,
        wins_delta: int = 0,
        round_id: int = None,
    ):
        rows = await db.execute_fetchall(
            "SELECT * FROM legacy_points WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )
        pts = submissions_delta + votes_received_delta + wins_delta * 5
        if rows:
            await db.execute("""
                UPDATE legacy_points SET
                    total_points=total_points+?,
                    submissions=submissions+?,
                    votes_received=votes_received+?,
                    wins=wins+?
                WHERE guild_id=? AND user_id=?
            """, (pts, submissions_delta, votes_received_delta, wins_delta, guild_id, user_id))
        else:
            await db.execute(
                "INSERT INTO legacy_points VALUES (?,?,?,?,?,?)",
                (guild_id, user_id, pts, submissions_delta, votes_received_delta, wins_delta)
            )

    # ────────────────────────────────────────────────────────────────
    # Legacy slash commands
    # ────────────────────────────────────────────────────────────────

    legacy = app_commands.Group(name="legacy", description="Legacy Points commands.")

    @legacy.command(name="profile", description="View your Legacy Points profile.")
    async def legacy_profile(self, interaction: discord.Interaction, member: discord.Member = None):
        gid = interaction.guild_id
        if not await is_enabled(gid, "legacy_points"):
            return await interaction.response.send_message(embed=not_enabled_embed("Legacy Points"), ephemeral=True)
        target = member or interaction.user
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM legacy_points WHERE guild_id=? AND user_id=?", (gid, target.id)
            )
        if not rows:
            return await interaction.response.send_message(
                embed=warning_embed("No Data", f"{target.display_name} has no Legacy Points yet."), ephemeral=True
            )
        r = rows[0]
        embed = base_embed(f"📜 Legacy Profile — {target.display_name}", colour=COLOUR_GOLD)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Total Points", value=f"**{r['total_points']}** pts", inline=True)
        embed.add_field(name="Submissions", value=str(r["submissions"]), inline=True)
        embed.add_field(name="Votes Received", value=str(r["votes_received"]), inline=True)
        embed.add_field(name="Wins 🏆", value=str(r["wins"]), inline=True)
        await interaction.response.send_message(embed=embed)

    @legacy.command(name="leaderboard", description="View the all-time Legacy Points leaderboard.")
    async def legacy_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "legacy_points"):
            return await interaction.response.send_message(embed=not_enabled_embed("Legacy Points"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, total_points, wins FROM legacy_points WHERE guild_id=? ORDER BY total_points DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No data yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"📜 {r['total_points']} pts · 🏆 {r['wins']} win(s)"))
        await interaction.response.send_message(embed=leaderboard_embed("📜 All-Time Legacy Leaderboard", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Comeback Counter
    # ────────────────────────────────────────────────────────────────

    comeback = app_commands.Group(name="comeback", description="Comeback Counter commands.")

    @comeback.command(name="leaderboard", description="View the Comeback Counter leaderboard.")
    async def comeback_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "comeback_counter"):
            return await interaction.response.send_message(embed=not_enabled_embed("Comeback Counter"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, comebacks FROM comeback_counter WHERE guild_id=? ORDER BY comebacks DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No comebacks yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"🎭 {r['comebacks']} comeback(s)"))
        await interaction.response.send_message(embed=leaderboard_embed("🎭 Comeback Counter", lb_rows))

    # ────────────────────────────────────────────────────────────────
    # Underdog Rising
    # ────────────────────────────────────────────────────────────────

    underdog = app_commands.Group(name="underdog", description="Underdog Rising leaderboard.")

    @underdog.command(name="leaderboard", description="Wins by members in the bottom half of Legacy Points.")
    async def underdog_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "underdog_rising"):
            return await interaction.response.send_message(embed=not_enabled_embed("Underdog Rising"), ephemeral=True)
        async with get_db() as db:
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
            lb_rows.append((i, name, f"⚡ {r['wins']} win(s) · {r['total_points']} pts total"))
        await interaction.response.send_message(embed=leaderboard_embed("⚡ Underdog Rising", lb_rows, colour=COLOUR_BRONZE))

    # ────────────────────────────────────────────────────────────────
    # The Grind
    # ────────────────────────────────────────────────────────────────

    grind = app_commands.Group(name="grind", description="The Grind — total submissions leaderboard.")

    @grind.command(name="leaderboard", description="Who has submitted the most, ever?")
    async def grind_lb(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not await is_enabled(gid, "the_grind"):
            return await interaction.response.send_message(embed=not_enabled_embed("The Grind"), ephemeral=True)
        async with get_db() as db:
            rows = await db.execute_fetchall(
                "SELECT user_id, submissions FROM legacy_points WHERE guild_id=? ORDER BY submissions DESC LIMIT 10",
                (gid,)
            )
        if not rows:
            return await interaction.response.send_message(embed=warning_embed("No Data", "No submissions yet."), ephemeral=True)
        lb_rows = []
        for i, r in enumerate(rows, 1):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"User {r['user_id']}"
            lb_rows.append((i, name, f"⚙️ {r['submissions']} submission(s)"))
        await interaction.response.send_message(embed=leaderboard_embed("⚙️ The Grind — Most Submissions", lb_rows))


async def setup(bot: commands.Bot):
    await bot.add_cog(LongGame(bot))
