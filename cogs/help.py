"""
Help cog — paginated /help command listing all commands with clickable mentions.
"""
import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import base_embed, COLOUR_PRIMARY

# (group_name, subcommand_name, description)
HELP_DATA = [
    {
        "title": "🛡️ Admin & Scheduling",
        "entries": [
            ("manage",   "enable",       "Enable a game on this server *(admin)*"),
            ("manage",   "disable",      "Disable a game on this server *(admin)*"),
            ("manage",   "setchannel",   "Set the dedicated channel for a game *(admin)*"),
            ("manage",   "clearchannel", "Remove the dedicated channel for a game *(admin)*"),
            ("manage",   "status",       "View all game settings for this server *(admin)*"),
            ("schedule", "add",          "Schedule a recurring task *(admin)*"),
            ("schedule", "remove",       "Remove a scheduled task *(admin)*"),
            ("schedule", "list",         "View all scheduled tasks *(admin)*"),
        ],
    },
    {
        "title": "🔥 Consistency & Dedication",
        "entries": [
            ("streak",      "checkin",     "Check in to keep your rolling streak alive"),
            ("streak",      "profile",     "View your rolling streak profile"),
            ("streak",      "leaderboard", "View the rolling streak leaderboard"),
            ("momentum",    "leaderboard", "View the Momentum Board"),
            ("persistence", "leaderboard", "View the Persistence Cup leaderboard"),
            ("faithful",    "leaderboard", "View The Faithful hall of fame"),
        ],
    },
    {
        "title": "🎯 Habits & Rituals",
        "entries": [
            ("prompt",        "post",        "Post today's daily prompt *(admin)*"),
            ("prompt",        "respond",     "Respond to the latest daily prompt"),
            ("prompt",        "leaderboard", "View the Daily Prompt leaderboard"),
            ("soldier",       "leaderboard", "View the Submission Soldier leaderboard"),
            ("vigilance",     "leaderboard", "View the Voter Vigilance leaderboard"),
            ("completionist", "leaderboard", "View The Completionist hall of fame"),
        ],
    },
    {
        "title": "🎨 Creative Rounds",
        "entries": [
            ("round", "open",   "Open a new creative round *(admin)*"),
            ("round", "close",  "Close the current round and tally results *(admin)*"),
            ("round", "submit", "Submit an entry to the current round"),
            ("round", "vote",   "Vote for a submission in the current round"),
            ("round", "status", "View the current round status"),
        ],
    },
    {
        "title": "📜 Legacy & Long Game",
        "entries": [
            ("legacy",   "profile",     "View your Legacy Points profile"),
            ("legacy",   "leaderboard", "View the all-time Legacy Points leaderboard"),
            ("comeback", "leaderboard", "View the Comeback Counter leaderboard"),
            ("underdog", "leaderboard", "View the Underdog Rising leaderboard"),
            ("grind",    "leaderboard", "View The Grind — total submissions leaderboard"),
        ],
    },
    {
        "title": "💬 Social",
        "entries": [
            ("hype",       "leaderboard", "View the Hype Keeper monthly vote leaderboard"),
            ("opposition", "leaderboard", "View the Loyal Opposition leaderboard"),
            ("shame",      "board",       "View the Streak Breaker hall of shame"),
        ],
    },
    {
        "title": "📊 Aggregated Leaderboards",
        "entries": [
            ("boards", "weekly",    "Rolling 7-day activity leaderboard"),
            ("boards", "monthly",   "Rolling 30-day activity leaderboard"),
            ("boards", "alltime",   "All-time Legacy Points leaderboard"),
            ("boards", "streaks",   "Current and all-time streak records"),
            ("boards", "voters",    "Most engaged voters leaderboard"),
            ("boards", "underdogs", "Wins by members in the bottom half of points"),
        ],
    },
]


class HelpView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=180)
        self.pages = pages
        self.current = 0
        self.author_id = author_id
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self.pages) - 1
        self.page_indicator.label = f"Page {self.current + 1} / {len(self.pages)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This help menu belongs to someone else. Run `/help` yourself!",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Page 1 / 7", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List all Tenacia bot commands.")
    async def help_cmd(self, interaction: discord.Interaction):
        try:
            synced = await self.bot.tree.fetch_commands()
        except Exception:
            synced = []

        cmd_ids: dict[str, int] = {cmd.name: cmd.id for cmd in synced}

        def mention(group: str, sub: str) -> str:
            cid = cmd_ids.get(group, 0)
            return f"</{group} {sub}:{cid}>"

        total = len(HELP_DATA)
        pages: list[discord.Embed] = []

        for i, page_data in enumerate(HELP_DATA, 1):
            embed = base_embed(page_data["title"], colour=COLOUR_PRIMARY)
            embed.set_footer(text=f"Tenacia · Page {i} of {total}")
            embed.description = "\n".join(
                f"{mention(group, sub)} — {desc}"
                for group, sub, desc in page_data["entries"]
            )
            pages.append(embed)

        view = HelpView(pages, interaction.user.id)
        await interaction.response.send_message(embed=pages[0], view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
