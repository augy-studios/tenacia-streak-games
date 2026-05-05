import aiosqlite
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "data/tenacia.db")

async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # ── Guild settings ───────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id    INTEGER NOT NULL,
                game_key    TEXT    NOT NULL,
                enabled     INTEGER NOT NULL DEFAULT 1,
                channel_id  INTEGER,
                PRIMARY KEY (guild_id, game_key)
            )
        """)

        # ── Streaks: Rolling Streak ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rolling_streak (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                last_checkin    REAL,           -- Unix timestamp
                current_streak  INTEGER NOT NULL DEFAULT 0,
                best_streak     INTEGER NOT NULL DEFAULT 0,
                total_checkins  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Streaks: Momentum Board ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS momentum_board (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                first_post_ts   REAL,
                last_post_ts    REAL,
                current_streak  INTEGER NOT NULL DEFAULT 0,
                best_streak     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Streaks: Persistence Cup (rolling 7-day windows) ─────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS persistence_cup (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                post_timestamps TEXT NOT NULL DEFAULT '[]',  -- JSON array of Unix timestamps
                qualifying_weeks INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Streaks: The Faithful (monthly activity) ─────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS the_faithful (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                months_active   INTEGER NOT NULL DEFAULT 0,
                active_months   TEXT NOT NULL DEFAULT '[]',  -- JSON array of "YYYY-MM" strings
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Habits: Daily Prompt Responder ───────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_prompts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                prompt_text     TEXT NOT NULL,
                posted_at       REAL NOT NULL,   -- Unix timestamp
                message_id      INTEGER
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_responses (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                prompt_id       INTEGER NOT NULL,
                responded_at    REAL NOT NULL,
                PRIMARY KEY (guild_id, user_id, prompt_id),
                FOREIGN KEY (prompt_id) REFERENCES daily_prompts(id)
            )
        """)

        # ── Habits: Submission Soldier (consecutive creative round submissions) ─
        await db.execute("""
            CREATE TABLE IF NOT EXISTS submission_soldier (
                guild_id            INTEGER NOT NULL,
                user_id             INTEGER NOT NULL,
                current_streak      INTEGER NOT NULL DEFAULT 0,
                best_streak         INTEGER NOT NULL DEFAULT 0,
                last_round_id       INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Habits: Voter Vigilance ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voter_vigilance (
                guild_id            INTEGER NOT NULL,
                user_id             INTEGER NOT NULL,
                voting_windows      INTEGER NOT NULL DEFAULT 0,
                last_voted_round    INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Habits: The Completionist ────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS completionist (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                achievements    INTEGER NOT NULL DEFAULT 0,
                last_achieved   REAL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Long Game: Legacy Points ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS legacy_points (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                total_points    INTEGER NOT NULL DEFAULT 0,
                submissions     INTEGER NOT NULL DEFAULT 0,
                votes_received  INTEGER NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Long Game: Comeback Counter ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS comeback_counter (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                comebacks       INTEGER NOT NULL DEFAULT 0,
                comeback_points INTEGER NOT NULL DEFAULT 0,
                last_submit_ts  REAL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Long Game: Underdog Rising ───────────────────────────────────
        # Uses legacy_points.wins filtered by bottom-half Legacy Points rank.
        # No extra table needed; queried dynamically.

        # ── Long Game: The Grind ─────────────────────────────────────────
        # Uses legacy_points.submissions.

        # ── Social: Hype Keeper (monthly vote count) ─────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hype_keeper (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                vote_timestamps TEXT NOT NULL DEFAULT '[]',  -- JSON array of Unix timestamps
                total_votes     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Social: Loyal Opposition ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS loyal_opposition (
                guild_id            INTEGER NOT NULL,
                user_id             INTEGER NOT NULL,
                contrarian_count    INTEGER NOT NULL DEFAULT 0,
                rounds_participated INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ── Social: Streak Breaker (hall of shame) ───────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS streak_breaker (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                broken_streak   INTEGER NOT NULL,
                broken_at       REAL NOT NULL
            )
        """)

        # ── Creative Rounds (shared by multiple games) ───────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS creative_rounds (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                round_name      TEXT NOT NULL,
                started_at      REAL NOT NULL,
                ended_at        REAL,
                is_open         INTEGER NOT NULL DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS round_submissions (
                round_id        INTEGER NOT NULL,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                submitted_at    REAL NOT NULL,
                PRIMARY KEY (round_id, guild_id, user_id),
                FOREIGN KEY (round_id) REFERENCES creative_rounds(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS round_votes (
                round_id        INTEGER NOT NULL,
                guild_id        INTEGER NOT NULL,
                voter_id        INTEGER NOT NULL,
                voted_for_id    INTEGER NOT NULL,
                voted_at        REAL NOT NULL,
                PRIMARY KEY (round_id, guild_id, voter_id),
                FOREIGN KEY (round_id) REFERENCES creative_rounds(id)
            )
        """)

        # ── Scheduler (SQLite-based) ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                task_type       TEXT NOT NULL,   -- e.g. 'daily_prompt'
                next_run        REAL NOT NULL,   -- Unix timestamp
                interval_secs   INTEGER NOT NULL,
                extra_data      TEXT             -- JSON blob
            )
        """)

        await db.commit()


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def ts_to_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)
