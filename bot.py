import discord
from discord.ext import commands
import asyncio
import logging
import os
import time
from dotenv import load_dotenv
from utils.db import init_db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("tenacia.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("tenacia")

COGS = [
    "cogs.admin",
    "cogs.streaks",
    "cogs.habits",
    "cogs.longgame",
    "cogs.social",
    "cogs.leaderboards",
    "cogs.scheduler",
    "cogs.help",
    "cogs.botinfo",
]

class Tenacia(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.start_time: float = time.time()

    async def setup_hook(self):
        await init_db()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}")
        await self.tree.sync()
        log.info("Slash commands synced globally.")

    async def _update_presence(self):
        guild_count = len(self.guilds)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{guild_count} guild{'s' if guild_count != 1 else ''} streaks"
            )
        )

    async def on_ready(self):
        self.start_time = time.time()
        log.info(f"Tenacia is online as {self.user} (ID: {self.user.id})")
        await self._update_presence()

    async def on_guild_join(self, guild: discord.Guild):
        log.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        await self._update_presence()

    async def on_guild_remove(self, guild: discord.Guild):
        log.info(f"Left guild: {guild.name} (ID: {guild.id})")
        await self._update_presence()

bot = Tenacia()

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN not set in environment.")
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
