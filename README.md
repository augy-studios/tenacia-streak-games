# <img src="/TSG-main.png" height="30" alt="icon"> Tenacia

A public Discord bot for consistency, dedication, and creative community games. Every feature can be independently enabled or disabled per server, with optional dedicated channels per game.

---

## Requirements

- Python 3.11+
- A Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))
- A Debian VPS (or any Linux machine)

---

## Setup

```bash
git clone https://github.com/yourname/tenacia.git
cd tenacia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # fill in DISCORD_TOKEN
mkdir -p data
```

---

## Running in tmux

```bash
tmux new-session -s tenacia
source .venv/bin/activate
python bot.py
# Detach: Ctrl+B, D
# Reattach later: tmux attach -t tenacia
```

Logs are written to `tenacia.log` and stdout simultaneously.

---

## Configuration

All settings are stored in SQLite (`data/tenacia.db`). No manual DB editing needed — everything is managed via slash commands.

### Per-server admin commands (requires Manage Server)

| Command | Description |
| --- | --- |
| `/manage enable <game>` | Enable a game on this server |
| `/manage disable <game>` | Disable a game on this server |
| `/manage setchannel <game> <channel>` | Set a dedicated channel for a game |
| `/manage clearchannel <game>` | Remove dedicated channel (use command channel) |
| `/manage status` | View all game settings for this server |
| `/schedule add <task> [interval_hours] [delay_minutes]` | Schedule a recurring task |
| `/schedule remove <task>` | Remove a scheduled task |
| `/schedule list` | View all scheduled tasks |

---

## Games

### Consistency & Dedication

#### Rolling Streak
Members check in once per personal 24-hour rolling window. The streak only breaks if their own 24-hour window lapses — completely timezone-independent.

| Command | Description |
| --- | --- |
| `/streak checkin` | Check in to keep your streak alive |
| `/streak profile [member]` | View streak profile |
| `/streak leaderboard` | View the streak leaderboard |

#### Momentum Board
Tracks consecutive days of posting at least once, measured in personal rolling windows. Each member's clock starts from their own first post.

| Command | Description |
| --- | --- |
| `/momentum leaderboard` | View the momentum board |

*Automatically tracked via message activity.*

#### Persistence Cup
Tracks weeks where a member posted on at least 5 out of any rolling 7 days. No fixed week start — fully personal.

| Command | Description |
| --- | --- |
| `/persistence leaderboard` | View the Persistence Cup leaderboard |

*Automatically tracked via message activity.*

#### The Faithful
Tracks how many total months a member has maintained activity. Never resets — long-term hall of fame for server loyalists.

| Command | Description |
| --- | --- |
| `/faithful leaderboard` | View The Faithful hall of fame |

*Automatically tracked via message activity and check-ins.*

---

### Habits & Rituals

#### Daily Prompt Responder
Bot posts a creative or discussion prompt every 24 hours (sourced from free public APIs). Members earn a point for responding to each one.

| Command | Description |
| --- | --- |
| `/prompt post` | Post today's prompt manually (admin) |
| `/prompt respond <response>` | Respond to the current prompt |
| `/prompt leaderboard` | View the prompt leaderboard |

**Scheduling the daily prompt:**

```bash
/schedule add daily_prompt interval_hours:24 delay_minutes:0
```

**Prompt APIs used (no key required):**
- [quotable.io](https://quotable.io) — inspirational quotes
- [uselessfacts.jsph.pl](https://uselessfacts.jsph.pl) — fun facts (fallback)

#### Submission Soldier
Tracks how many consecutive creative rounds a member has submitted an entry to. Misses break the streak.

| Command | Description |
| --- | --- |
| `/soldier leaderboard` | View the Submission Soldier leaderboard |

*Automatically updated when rounds close.*

#### Voter Vigilance
Tracks how many voting windows (rounds) a member has participated in. Separate from winners — rewards the people who show up to judge.

| Command | Description |
| --- | --- |
| `/vigilance leaderboard` | View the Voter Vigilance leaderboard |

*Automatically updated when rounds close.*

#### The Completionist
Tracks members who both submitted AND voted in every round. Permanently recorded hall of fame.

| Command | Description |
| --- | --- |
| `/completionist leaderboard` | View The Completionist hall of fame |

*Automatically updated when rounds close.*

---

### Long Game

#### Creative Rounds
The foundation for submission, voting, Legacy Points, and related games.

| Command | Description |
| --- | --- |
| `/round open <name>` | Open a new creative round (admin) |
| `/round close` | Close the current round and tally results (admin) |
| `/round submit <content>` | Submit an entry to the current round |
| `/round vote <member>` | Vote for a member's submission |
| `/round status` | View current round status |

#### Legacy Points
Every submission earns 1 point. Every vote received earns 1 point. Every win earns 5 points. All-time, never resets.

| Command | Description |
| --- | --- |
| `/legacy profile [member]` | View Legacy Points profile |
| `/legacy leaderboard` | View the all-time Legacy leaderboard |

#### Comeback Counter
Tracks members who returned to submit after a 14+ day absence. Each comeback earns a dramatic return announcement.

| Command | Description |
| --- | --- |
| `/comeback leaderboard` | View the Comeback Counter leaderboard |

#### Underdog Rising
Separate leaderboard tracking wins earned by members in the bottom half of Legacy Points.

| Command | Description |
| --- | --- |
| `/underdog leaderboard` | View the Underdog Rising leaderboard |

#### The Grind
Tracks total number of submissions ever made regardless of wins. Raw volume, all-time.

| Command | Description |
| --- | --- |
| `/grind leaderboard` | View The Grind leaderboard |

---

### Social Consistency

#### Hype Keeper
Tracks how many times each member voted in any round over the rolling month. Crowns the most engaged audience member.

| Command | Description |
| --- | --- |
| `/hype leaderboard` | View the Hype Keeper leaderboard |

#### Loyal Opposition
Tracks members who consistently vote against the majority (picked the losing side) but still show up every round.

| Command | Description |
| --- | --- |
| `/opposition leaderboard` | View the Loyal Opposition leaderboard |

#### Streak Breaker
Hall of shame tracking whose submission streak got broken and how long they'd gone. Purely for commiseration.

| Command | Description |
|---|---|
| `/shame board` | View the Streak Breaker hall of shame |

---

### Aggregated Leaderboards

| Command | Description |
| --- | --- |
| `/boards weekly` | Rolling 7-day activity leaderboard |
| `/boards monthly` | Rolling 30-day activity leaderboard |
| `/boards alltime` | All-time Legacy Points board |
| `/boards streaks` | Current + all-time streak records |
| `/boards voters` | Most engaged voters (all-time) |
| `/boards underdogs` | Wins by bottom-half Legacy members |

---

## Project Structure

```bash
tenacia/
├── bot.py              # Entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── data/               # SQLite database (gitignored)
├── utils/
│   ├── db.py           # Database init & helpers
│   ├── settings.py     # Per-guild game enable/disable/channel
│   └── embeds.py       # Embed factory
└── cogs/
    ├── admin.py        # /manage and /schedule commands
    ├── streaks.py      # Rolling Streak, Momentum, Persistence, Faithful
    ├── habits.py       # Daily Prompt, Submission Soldier, Voter Vigilance, Completionist
    ├── longgame.py     # Rounds, Legacy Points, Comeback, Underdog, Grind
    ├── social.py       # Hype Keeper, Loyal Opposition, Streak Breaker
    ├── leaderboards.py # Aggregated board commands
    └── scheduler.py    # SQLite-based recurring task runner
```

---

## Inviting Tenacia

When creating your bot on the Discord Developer Portal:

- **Scopes:** `bot`, `applications.commands`
- **Permissions:** Send Messages, Embed Links, Read Message History, View Channels
- **Privileged Intents:** Server Members Intent, Message Content Intent

---

## License

MIT
