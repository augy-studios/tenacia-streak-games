"""
Centralised embed factory for Tenacia.
Keeps visual style consistent across all cogs.
"""
import discord
from datetime import datetime, timezone

COLOUR_PRIMARY   = 0x5865F2   # Discord blurple
COLOUR_SUCCESS   = 0x57F287
COLOUR_WARNING   = 0xFEE75C
COLOUR_DANGER    = 0xED4245
COLOUR_NEUTRAL   = 0x99AAB5
COLOUR_GOLD      = 0xF1C40F
COLOUR_BRONZE    = 0xCD7F32


def base_embed(
    title: str,
    description: str = "",
    colour: int = COLOUR_PRIMARY,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        colour=colour,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Tenacia")
    return embed


def success_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(title, description, COLOUR_SUCCESS)


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(title, description, COLOUR_WARNING)


def danger_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(title, description, COLOUR_DANGER)


def leaderboard_embed(
    title: str,
    rows: list[tuple[int, str, str]],   # (rank, label, value)
    description: str = "",
    colour: int = COLOUR_GOLD,
) -> discord.Embed:
    embed = base_embed(title, description, colour)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for rank, label, value in rows[:10]:
        prefix = medals.get(rank, f"`#{rank}`")
        embed.add_field(name=f"{prefix} {label}", value=value, inline=False)
    return embed


def not_enabled_embed(game_name: str) -> discord.Embed:
    return warning_embed(
        "Game Not Enabled",
        f"**{game_name}** is not enabled on this server.\n"
        "An admin can enable it with `/manage enable`."
    )
