"""
Helpers for per-guild game enable/disable and channel assignment.
"""
import aiosqlite
from utils.db import get_db

# All valid game keys
GAME_KEYS = [
    # Consistency & Dedication
    "rolling_streak",
    "momentum_board",
    "persistence_cup",
    "the_faithful",
    # Habits & Rituals
    "daily_prompt",
    "submission_soldier",
    "voter_vigilance",
    "completionist",
    # Long Game
    "legacy_points",
    "comeback_counter",
    "underdog_rising",
    "the_grind",
    # Social
    "hype_keeper",
    "loyal_opposition",
    "streak_breaker",
    # Leaderboards
    "weekly_board",
    "monthly_board",
    "alltime_board",
    "streak_board",
    "voter_board",
    "underdog_board",
]

GAME_DISPLAY = {
    "rolling_streak":      "Rolling Streak",
    "momentum_board":      "Momentum Board",
    "persistence_cup":     "Persistence Cup",
    "the_faithful":        "The Faithful",
    "daily_prompt":        "Daily Prompt Responder",
    "submission_soldier":  "Submission Soldier",
    "voter_vigilance":     "Voter Vigilance",
    "completionist":       "The Completionist",
    "legacy_points":       "Legacy Points",
    "comeback_counter":    "Comeback Counter",
    "underdog_rising":     "Underdog Rising",
    "the_grind":           "The Grind",
    "hype_keeper":         "Hype Keeper",
    "loyal_opposition":    "Loyal Opposition",
    "streak_breaker":      "Streak Breaker",
    "weekly_board":        "Weekly Leaderboard",
    "monthly_board":       "Monthly Leaderboard",
    "alltime_board":       "All-Time Legacy Board",
    "streak_board":        "Streak Board",
    "voter_board":         "Voter Board",
    "underdog_board":      "Underdog Board",
}


async def is_enabled(guild_id: int, game_key: str) -> bool:
    async with get_db() as db:
        row = await db.execute_fetchall(
            "SELECT enabled FROM guild_settings WHERE guild_id=? AND game_key=?",
            (guild_id, game_key)
        )
    if not row:
        return True  # Default: enabled
    return bool(row[0]["enabled"])


async def set_enabled(guild_id: int, game_key: str, enabled: bool):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO guild_settings (guild_id, game_key, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, game_key) DO UPDATE SET enabled=excluded.enabled
        """, (guild_id, game_key, int(enabled)))
        await db.commit()


async def get_channel(guild_id: int, game_key: str) -> int | None:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT channel_id FROM guild_settings WHERE guild_id=? AND game_key=?",
            (guild_id, game_key)
        )
    if not rows:
        return None
    return rows[0]["channel_id"]


async def set_channel(guild_id: int, game_key: str, channel_id: int | None):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO guild_settings (guild_id, game_key, channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, game_key) DO UPDATE SET channel_id=excluded.channel_id
        """, (guild_id, game_key, channel_id))
        await db.commit()


async def get_all_settings(guild_id: int) -> dict:
    """Returns dict of game_key -> {enabled, channel_id}"""
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT game_key, enabled, channel_id FROM guild_settings WHERE guild_id=?",
            (guild_id,)
        )
    result = {k: {"enabled": True, "channel_id": None} for k in GAME_KEYS}
    for row in rows:
        result[row["game_key"]] = {
            "enabled": bool(row["enabled"]),
            "channel_id": row["channel_id"],
        }
    return result
