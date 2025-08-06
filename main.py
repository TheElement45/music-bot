# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import asyncio
import logging
import os
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
COMMAND_PREFIX = "-"

# --- Logging Setup ---
# Keep logging setup as before
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)
os.makedirs('logs', exist_ok=True)
handler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_logger.addHandler(handler)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        self.logger = discord_logger # Make logger accessible

    async def setup_hook(self):
        """Loads extensions (cogs) before the bot connects."""
        initial_extensions = [
            'cogs.music_cog'
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f'Successfully loaded extension: {extension}')
            except Exception as e:
                print(f'Failed to load extension {extension}.')
                self.logger.error(f"Error loading extension {extension}", exc_info=e)

    async def on_ready(self):
        print(f'Logged in as {self.user.name} (ID: {self.user.id})')
        print('------')
        await self.change_presence(activity=discord.Game(name=f"music | {COMMAND_PREFIX}help"))

    async def on_command_error(self, ctx, error):
        """Global command error handler"""
        if isinstance(error, commands.CommandNotFound):
            pass # Ignore command not found
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument(s). Usage: `{COMMAND_PREFIX}{ctx.command.name} {ctx.command.signature}`", delete_after=15)
        elif isinstance(error, commands.NotOwner):
            await ctx.send("Owner command only.", delete_after=15)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f"Missing perms: `{'`, `'.join(error.missing_permissions)}`", delete_after=15)
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            self.logger.error(f"Cmd '{ctx.command.name}' invoke error: {original}", exc_info=original)
            await ctx.send(f"Command Error: `{type(original).__name__}`. Check logs.", delete_after=15)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Cooldown. Try again in {error.retry_after:.2f}s.", delete_after=10)
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("Requirements not met.", delete_after=15)
        else:
            # Log any other errors that weren't caught by cogs
            self.logger.error(f"Unhandled command error in global handler: {error}", exc_info=error)


bot = MusicBot()

# --- Run the Bot ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not found in .env file or environment variables.")
    else:
        try:
            # Use asyncio.run() to start the bot runner
            # Remove log_handler from start() as it's not a valid argument
            asyncio.run(bot.start(BOT_TOKEN)) # Corrected line
        except discord.LoginFailure:
            print("LOGIN FAILED: Check if the DISCORD_BOT_TOKEN is correct.")
            bot.logger.critical("LOGIN FAILED: Invalid Token.")
        except discord.PrivilegedIntentsRequired:
             print("PRIVILEGED INTENTS ERROR: Ensure 'MESSAGE CONTENT INTENT' is enabled.")
             bot.logger.critical("PRIVILEGED INTENTS ERROR: Message Content Intent missing.")
        except Exception as e:
            print(f"FATAL ERROR starting bot: {e}")
            bot.logger.critical(f"FATAL ERROR starting bot: {e}", exc_info=True)