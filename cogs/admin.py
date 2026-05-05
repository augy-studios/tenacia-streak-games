"""
Admin cog — manage game toggles and channel assignments per guild.
Requires Manage Channels permission.
"""
import discord
from discord import app_commands
from discord.ext import commands
from utils.settings import (
    GAME_KEYS, GAME_DISPLAY,
    is_enabled, set_enabled,
    get_channel, set_channel,
    get_all_settings,
)
from utils.embeds import (
    success_embed, warning_embed, danger_embed, base_embed,
    COLOUR_PRIMARY, COLOUR_NEUTRAL,
)


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                embed=danger_embed("No Permission", "You need **Manage Channels** permission."),
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)


game_key_choices = [
    app_commands.Choice(name=GAME_DISPLAY[k], value=k)
    for k in GAME_KEYS
]


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    manage = app_commands.Group(name="manage", description="Manage Tenacia games for this server.")

    @manage.command(name="enable", description="Enable a game on this server.")
    @app_commands.describe(game="Which game to enable")
    @app_commands.choices(game=game_key_choices)
    @admin_only()
    async def enable_game(self, interaction: discord.Interaction, game: app_commands.Choice[str]):
        await set_enabled(interaction.guild_id, game.value, True)
        await interaction.response.send_message(
            embed=success_embed("Game Enabled", f"**{game.name}** has been enabled on this server."),
            ephemeral=True,
        )

    @manage.command(name="disable", description="Disable a game on this server.")
    @app_commands.describe(game="Which game to disable")
    @app_commands.choices(game=game_key_choices)
    @admin_only()
    async def disable_game(self, interaction: discord.Interaction, game: app_commands.Choice[str]):
        await set_enabled(interaction.guild_id, game.value, False)
        await interaction.response.send_message(
            embed=warning_embed("Game Disabled", f"**{game.name}** has been disabled on this server."),
            ephemeral=True,
        )

    @manage.command(name="setchannel", description="Set the dedicated channel for a game.")
    @app_commands.describe(game="Which game", channel="Channel to use")
    @app_commands.choices(game=game_key_choices)
    @admin_only()
    async def set_game_channel(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        await set_channel(interaction.guild_id, game.value, channel.id)
        await interaction.response.send_message(
            embed=success_embed(
                "Channel Set",
                f"**{game.name}** posts will go to {channel.mention}."
            ),
            ephemeral=True,
        )

    @manage.command(name="clearchannel", description="Remove the dedicated channel for a game (uses current channel).")
    @app_commands.describe(game="Which game")
    @app_commands.choices(game=game_key_choices)
    @admin_only()
    async def clear_game_channel(self, interaction: discord.Interaction, game: app_commands.Choice[str]):
        await set_channel(interaction.guild_id, game.value, None)
        await interaction.response.send_message(
            embed=success_embed("Channel Cleared", f"**{game.name}** will now use the channel where commands are run."),
            ephemeral=True,
        )

    @manage.command(name="status", description="View the current settings for all games on this server.")
    @admin_only()
    async def status(self, interaction: discord.Interaction):
        settings = await get_all_settings(interaction.guild_id)
        embed = base_embed("Server Game Settings", colour=COLOUR_PRIMARY)

        categories = {
            "📊 Consistency & Dedication": ["rolling_streak", "momentum_board", "persistence_cup", "the_faithful"],
            "🎯 Habits & Rituals": ["daily_prompt", "submission_soldier", "voter_vigilance", "completionist"],
            "🏆 Long Game": ["legacy_points", "comeback_counter", "underdog_rising", "the_grind"],
            "💬 Social": ["hype_keeper", "loyal_opposition", "streak_breaker"],
            "📋 Leaderboards": ["weekly_board", "monthly_board", "alltime_board", "streak_board", "voter_board", "underdog_board"],
        }

        for cat, keys in categories.items():
            lines = []
            for k in keys:
                s = settings[k]
                icon = "✅" if s["enabled"] else "❌"
                ch = f" → <#{s['channel_id']}>" if s["channel_id"] else ""
                lines.append(f"{icon} **{GAME_DISPLAY[k]}**{ch}")
            embed.add_field(name=cat, value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
