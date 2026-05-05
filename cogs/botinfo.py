import discord
from discord import app_commands
from discord.ext import commands
import platform
import socket
import time
import psutil
from utils.embeds import base_embed, COLOUR_PRIMARY


def _count_commands(cmds) -> int:
    total = 0
    for cmd in cmds:
        if isinstance(cmd, app_commands.Group):
            total += _count_commands(cmd.commands)
        else:
            total += 1
    return total


class BotInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="botinfo", description="View information about this bot.")
    async def botinfo(self, interaction: discord.Interaction):
        uname = platform.uname()
        os_info = f"{uname.system} {uname.release}"

        uptime_secs = int(time.time() - self.bot.start_time)
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

        hostname = socket.gethostname()
        cpu_arch = platform.machine()
        cpu_cores = psutil.cpu_count(logical=True) or 1
        cpu_usage = psutil.cpu_percent(interval=0.1)

        mem = psutil.virtual_memory()
        mem_used_mb = mem.used / (1024 ** 2)
        mem_total_gb = mem.total / (1024 ** 3)

        python_ver = platform.python_version()
        dpy_ver = discord.__version__

        guild_count = len(self.bot.guilds)
        channel_count = sum(len(g.channels) for g in self.bot.guilds)
        user_count = sum(g.member_count or 0 for g in self.bot.guilds)

        total_commands = _count_commands(self.bot.tree.get_commands())

        embed = base_embed("Bot Information")
        embed.add_field(name="Operating System",   value=os_info,                                                inline=False)
        embed.add_field(name="Uptime",             value=uptime_str,                                             inline=False)
        embed.add_field(name="Hostname",           value=hostname,                                               inline=False)
        embed.add_field(name="CPU Architecture",   value=f"{cpu_arch} ({cpu_cores} cores)",                      inline=False)
        embed.add_field(name="CPU Usage",          value=f"{cpu_usage:.0f}%",                                    inline=False)
        embed.add_field(name="Memory Usage",       value=f"{mem_used_mb:.2f}MB / {mem_total_gb:.2f}GB",          inline=False)
        embed.add_field(name="Python Version",     value=f"v{python_ver}",                                       inline=False)
        embed.add_field(name="discord.py Version", value=dpy_ver,                                                inline=False)
        embed.add_field(name="Connected to",       value=f"{guild_count} guilds, {channel_count} channels, and {user_count} users", inline=False)
        embed.add_field(name="Total Commands",     value=str(total_commands),                                    inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotInfo(bot))
