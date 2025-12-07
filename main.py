# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import asyncio
import logging
import logging.handlers
import os
import signal
import sys

# Import centralized config
import config

# --- Logging Setup ---
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
os.makedirs('logs', exist_ok=True)

# Add rotating file handler
handler = logging.handlers.TimedRotatingFileHandler(
    filename=config.LOG_FILE,
    encoding='utf-8',
    when=config.LOG_ROTATION,
    backupCount=config.LOG_BACKUP_COUNT
)
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_logger.addHandler(handler)

# Also add console handler for development
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_logger.addHandler(console_handler)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)
        self.logger = discord_logger # Make logger accessible
        self._shutdown_flag = False

    async def setup_hook(self):
        """Loads extensions (cogs) before the bot connects."""
        initial_extensions = [
            'cogs.music'  # New refactored music module
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f'Successfully loaded extension: {extension}')
            except Exception as e:
                print(f'Failed to load extension {extension}.')
                self.logger.error(f"Error loading extension {extension}", exc_info=e)

    async def on_ready(self):
        if self.user is not None:
            print(f'Logged in as {self.user.name} (ID: {self.user.id})')
        else:
            print('Logged in, but self.user is None.')
        print('------')
        await self.change_presence(activity=discord.Game(name=f"music | {config.COMMAND_PREFIX}help"))
    
    async def shutdown(self):
        """Gracefully shutdown the bot"""
        if self._shutdown_flag:
            return
        self._shutdown_flag = True
        
        self.logger.info("Shutting down bot...")
        
        # Disconnect from all voice channels
        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except:
                pass
        
        # Close the bot
        await self.close()

    async def on_command_error(self, ctx, error):
        """Global command error handler"""
        if isinstance(error, commands.CommandNotFound):
            pass # Ignore command not found
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument(s). Usage: `{config.COMMAND_PREFIX}{ctx.command.name} {ctx.command.signature}`", delete_after=15)
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

# --- Signal handlers for graceful shutdown ---
def handle_shutdown(signum, frame):
    """Handle shutdown signals"""
    print("\nReceived shutdown signal, closing bot...")
    asyncio.create_task(bot.shutdown())

# --- Run the Bot ---
if __name__ == "__main__":
    if not config.BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not found in .env file or environment variables.")
        sys.exit(1)
    
    # Register signal handlers
    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception as e:
        print(f"Warning: Could not register signal handlers: {e}")
    
    try:
        # Use asyncio.run() to start the bot
        asyncio.run(bot.start(config.BOT_TOKEN))
    except discord.LoginFailure:
        print("LOGIN FAILED: Check if the DISCORD_BOT_TOKEN is correct.")
        bot.logger.critical("LOGIN FAILED: Invalid Token.")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        print("PRIVILEGED INTENTS ERROR: Ensure 'MESSAGE CONTENT INTENT' is enabled.")
        bot.logger.critical("PRIVILEGED INTENTS ERROR: Message Content Intent missing.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"FATAL ERROR starting bot: {e}")
        bot.logger.critical(f"FATAL ERROR starting bot: {e}", exc_info=True)
        sys.exit(1)