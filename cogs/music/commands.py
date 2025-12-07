# -*- coding: utf-8 -*-
"""
Music commands - thin layer delegating to services
"""

import asyncio
import logging
import os
import time
from typing import Optional

import discord
from discord.ext import commands

import config
from models.song import Song
from services.extractor import ExtractorService
from services.queue import QueueService
from services.player import PlayerService
from utils.database import RedisManager
from utils.cache import GuildCache
from utils.lyrics import LyricsProvider
from utils.helpers import format_duration, parse_time

from .views import MusicControlView
from .embeds import EmbedBuilder


logger = logging.getLogger('music_bot')


class MusicCommands(commands.Cog):
    """Music commands cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger
        self.start_time = time.time()
        
        # Initialize services
        self.db = RedisManager(host=os.getenv('REDIS_HOST', 'redis'))
        self.queue_service = QueueService(self.db)
        self.extractor = ExtractorService()
        self.player = PlayerService(bot, self.queue_service, self.extractor)
        
        # Utilities
        self.cache = GuildCache()
        self.lyrics_provider = LyricsProvider()
    
    def _after_play(self, guild_id: int):
        """Create after callback for playback"""
        def callback(error):
            if error:
                self.logger.error(f"Player error: {error}")
            # Schedule next song
            asyncio.run_coroutine_threadsafe(
                self._play_next_async(guild_id),
                self.bot.loop
            )
        return callback
    
    async def _play_next_async(self, guild_id: int):
        """Async wrapper to play next song"""
        success = await self.player.play_next(guild_id, self._after_play(guild_id))
        
        if not success:
            # Queue is empty - check if autoplay is enabled
            if self.queue_service.get_autoplay(guild_id):
                current = self.queue_service.get_current(guild_id)
                if current:
                    self.logger.info(f"Auto-play: fetching recommendations for {current.title}")
                    related = await self.extractor.get_related_songs(current, limit=3)
                    if related:
                        self.queue_service.add_many(guild_id, related)
                        # Try playing again
                        success = await self.player.play_next(guild_id, self._after_play(guild_id))
                        if success:
                            return
            
            self.queue_service.clear_now_playing_message(guild_id)
    
    async def _send_now_playing(self, ctx, song: Song):
        """Send now playing embed with controls"""
        embed = EmbedBuilder.now_playing(song)
        view = MusicControlView(self)
        view.update_buttons(ctx.guild.id)
        message = await ctx.send(embed=embed, view=view)
        view.message = message
        self.queue_service.set_now_playing_message(ctx.guild.id, message.id)
    
    # --- Listeners ---
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info(f'Music Cog ready as {self.bot.user}')
        # Restore queues from Redis
        for guild in self.bot.guilds:
            self.queue_service.get_state(guild.id)  # This loads from Redis
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Bot disconnected
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            
            if self.player.is_intentional_disconnect(guild_id):
                self.logger.info(f"Intentional disconnect G:{guild_id}")
                return
            
            self.logger.info(f"Bot disconnected from VC G:{guild_id}")
            self.queue_service.cleanup_guild(guild_id)
            return
        
        # Check if bot is alone (skip if 24/7 mode)
        if not member.bot and before.channel != after.channel:
            if before.channel:
                bot_in_channel = any(m.id == self.bot.user.id for m in before.channel.members)
                if bot_in_channel:
                    non_bots = [m for m in before.channel.members if not m.bot]
                    if not non_bots:
                        guild_id = before.channel.guild.id
                        # Check 24/7 mode
                        if self.queue_service.get_247_mode(guild_id):
                            self.logger.info(f"24/7 mode enabled, staying in {before.channel.name}")
                            return
                        
                        vc = self.player.get_voice_client(guild_id)
                        if vc:
                            self.logger.info(f"Bot alone in {before.channel.name}, disconnecting...")
                            await self.player.disconnect(guild_id)
    
    # --- Commands ---
    
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.command(name='play', aliases=['p'], help='Plays a song from YouTube.')
    async def play(self, ctx, *, query: str):
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel!", delete_after=10)
            return
        
        target_channel = ctx.author.voice.channel
        vc = ctx.voice_client
        
        # Connect if needed
        if not vc:
            vc = await self.player.connect(target_channel)
            if not vc:
                await ctx.send("Could not connect to voice channel.", delete_after=10)
                return
        elif vc.channel != target_channel:
            await vc.move_to(target_channel)
        
        # Extract song info
        async with ctx.typing():
            results = await self.extractor.extract(query, ctx.author)
        
        if isinstance(results, dict) and 'error' in results:
            await ctx.send(f"Error: {results['error']}", delete_after=15)
            return
        
        if not results:
            await ctx.send("No results found.", delete_after=10)
            return
        
        guild_id = ctx.guild.id
        
        # Add to queue
        if len(results) == 1:
            position = self.queue_service.add(guild_id, results[0])
            await ctx.send(f"Added **{results[0].title}** to queue (#{position}).")
        else:
            count = self.queue_service.add_many(guild_id, results)
            msg = f"Added {count} songs to queue."
            
            # Load remaining playlist in background if needed
            if count >= 20:
                msg += " Loading more in background..."
                asyncio.create_task(self._load_remaining_playlist(ctx, query, count))
            
            await ctx.send(msg)
        
        # Start playing if not already
        if not self.player.is_playing(guild_id) and not self.player.is_paused(guild_id):
            success = await self.player.play_next(guild_id, self._after_play(guild_id))
            if success:
                current = self.queue_service.get_current(guild_id)
                if current:
                    await self._send_now_playing(ctx, current)
    
    async def _load_remaining_playlist(self, ctx, query: str, loaded_count: int):
        """Background task to load remaining playlist songs"""
        songs = await self.extractor.extract_remaining_playlist(query, loaded_count, ctx.author)
        if songs:
            self.queue_service.add_many(ctx.guild.id, songs)
            await ctx.send(f"✅ Loaded {len(songs)} more songs from playlist.")
    
    @commands.cooldown(1, 2, commands.BucketType.user)
    @commands.command(name='skip', aliases=['s'], help='Skips the current song.')
    async def skip(self, ctx):
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        if not vc or not (self.player.is_playing(guild_id) or self.player.is_paused(guild_id)):
            await ctx.send("Nothing to skip.", delete_after=10)
            return
        
        current = self.queue_service.get_current(guild_id)
        is_admin = ctx.author.guild_permissions.manage_channels
        is_requester = current and current.requester and ctx.author.id == current.requester.id
        
        # Vote skip logic
        if not is_admin and not is_requester:
            listeners = [m for m in vc.channel.members if not m.bot]
            required = max(1, int(len(listeners) * config.VOTE_SKIP_THRESHOLD))
            
            if not self.queue_service.add_skip_vote(guild_id, ctx.author.id):
                await ctx.send("You already voted to skip!", delete_after=5)
                return
            
            votes = self.queue_service.get_skip_votes(guild_id)
            if votes < required:
                await ctx.send(f"🗳️ Vote to skip: {votes}/{required}")
                return
            
            await ctx.send("🗳️ Vote passed! Skipping...")
        
        await ctx.message.add_reaction('⏭️')
        await self.player.skip(guild_id)
    
    @commands.command(name='stop', help='Stops playback and clears queue.')
    async def stop(self, ctx):
        guild_id = ctx.guild.id
        self.queue_service.clear(guild_id)
        await self.player.skip(guild_id)
        await ctx.send("Stopped and cleared queue. ⏹️")
    
    @commands.command(name='pause', help='Pauses the currently playing song.')
    async def pause(self, ctx):
        if self.player.pause(ctx.guild.id):
            await ctx.message.add_reaction('⏸️')
        elif self.player.is_paused(ctx.guild.id):
            await ctx.send("Already paused.")
        else:
            await ctx.send("Nothing playing.")
    
    @commands.command(name='resume', help='Resumes the currently paused song.')
    async def resume(self, ctx):
        if self.player.resume(ctx.guild.id):
            await ctx.message.add_reaction('▶️')
        elif self.player.is_playing(ctx.guild.id):
            await ctx.send("Already playing.")
        else:
            await ctx.send("Nothing paused.")
    
    @commands.command(name='volume', aliases=['vol'], help='Sets the volume (0-100).')
    async def set_volume(self, ctx, volume: int):
        if not 0 <= volume <= 100:
            await ctx.send("Volume must be between 0 and 100.")
            return
        
        self.queue_service.set_volume(ctx.guild.id, volume / 100)
        await ctx.send(f"Volume set to {volume}% 🔊")
    
    @commands.command(name='loop', help='Cycles loop mode.')
    async def loop(self, ctx):
        new_mode = self.queue_service.cycle_loop_mode(ctx.guild.id)
        await ctx.send(f"Loop mode: **{new_mode}**")
    
    @commands.command(name='queue', aliases=['q'], help='Display the current song queue.')
    async def queue(self, ctx, page: int = 1):
        guild_id = ctx.guild.id
        queue = self.queue_service.get_queue(guild_id)
        current = self.queue_service.get_current(guild_id)
        
        if not queue and not current:
            await ctx.send("The queue is empty.", delete_after=10)
            return
        
        items_per_page = 10
        total_pages = max(1, (len(queue) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))
        
        embed = EmbedBuilder.queue(current, queue, page, total_pages)
        await ctx.send(embed=embed)
    
    @commands.command(name='nowplaying', aliases=['np'], help='Show the currently playing song.')
    async def nowplaying(self, ctx):
        guild_id = ctx.guild.id
        current = self.queue_service.get_current(guild_id)
        
        if not current:
            await ctx.send("Nothing is currently playing.", delete_after=10)
            return
        
        elapsed = self.player.get_current_position(guild_id)
        embed = EmbedBuilder.now_playing_detailed(
            current,
            elapsed,
            self.queue_service.get_loop_mode(guild_id),
            self.queue_service.get_volume(guild_id),
            len(self.queue_service.get_queue(guild_id))
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='seek', help='Seek to a specific timestamp.')
    async def seek(self, ctx, timestamp: str):
        guild_id = ctx.guild.id
        
        if not self.player.is_playing(guild_id) and not self.player.is_paused(guild_id):
            await ctx.send("Nothing is playing.", delete_after=10)
            return
        
        seconds = parse_time(timestamp)
        if seconds is None:
            await ctx.send("❌ Invalid format. Use MM:SS or seconds.")
            return
        
        current = self.queue_service.get_current(guild_id)
        if current and current.duration and seconds > current.duration:
            await ctx.send("❌ Timestamp exceeds song duration.")
            return
        
        await ctx.send(f"⏩ Seeking to **{format_duration(seconds)}**...")
        success = await self.player.seek(guild_id, seconds, self._after_play(guild_id))
        
        if not success:
            await ctx.send("❌ Could not seek.")
    
    @commands.command(name='shuffle', help='Shuffles the current song queue.')
    async def shuffle(self, ctx):
        guild_id = ctx.guild.id
        queue = self.queue_service.get_queue(guild_id)
        
        if len(queue) < 2:
            await ctx.send("Not enough songs to shuffle.", delete_after=10)
            return
        
        self.queue_service.shuffle(guild_id)
        await ctx.send("🔀 Queue shuffled!")
        await ctx.message.add_reaction('✅')
    
    @commands.command(name='remove', aliases=['rm'], help='Removes a song from the queue.')
    async def remove(self, ctx, index: int):
        guild_id = ctx.guild.id
        queue = self.queue_service.get_queue(guild_id)
        
        if not queue:
            await ctx.send("Queue is empty.", delete_after=10)
            return
        
        if not 1 <= index <= len(queue):
            await ctx.send(f"Invalid index. Must be 1-{len(queue)}.", delete_after=10)
            return
        
        removed = self.queue_service.remove(guild_id, index - 1)
        if removed:
            await ctx.send(f"🗑️ Removed **{removed.title}** (#{index}).")
            await ctx.message.add_reaction('✅')
    
    @commands.command(name='move', help='Move a song in the queue.')
    async def move(self, ctx, from_pos: int, to_pos: int):
        guild_id = ctx.guild.id
        queue = self.queue_service.get_queue(guild_id)
        
        if not queue:
            await ctx.send("Queue is empty.", delete_after=10)
            return
        
        if not (1 <= from_pos <= len(queue) and 1 <= to_pos <= len(queue)):
            await ctx.send(f"Invalid positions. Queue has {len(queue)} songs.", delete_after=10)
            return
        
        song = queue[from_pos - 1]
        self.queue_service.move(guild_id, from_pos - 1, to_pos - 1)
        await ctx.send(f"✅ Moved **{song.title}** from #{from_pos} to #{to_pos}")
    
    @commands.command(name='filter', aliases=['effect'], help='Apply audio filter.')
    async def filter_cmd(self, ctx, filter_name: str):
        valid_filters = ['off', 'nightcore', 'vaporwave', 'bassboost', '8d', 'karaoke']
        
        if filter_name.lower() not in valid_filters:
            await ctx.send(f"❌ Invalid filter. Available: {', '.join(valid_filters)}")
            return
        
        await ctx.send(f"🎵 Applying **{filter_name}** filter...")
        success = await self.player.apply_filter(
            ctx.guild.id, 
            filter_name.lower(),
            self._after_play(ctx.guild.id)
        )
        
        if not success:
            await ctx.send("❌ Could not apply filter.")
    
    @commands.command(name='disconnect', aliases=['leave', 'dc'], help='Disconnect from voice.')
    async def disconnect(self, ctx):
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        if not vc:
            await ctx.send("I'm not in a voice channel.", delete_after=10)
            return
        
        await self.player.disconnect(guild_id)
        await ctx.send("👋 Disconnected.")
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(name='lyrics', help='Get lyrics for a song.')
    async def lyrics(self, ctx, *, query: str = None):
        if not query:
            current = self.queue_service.get_current(ctx.guild.id)
            if current:
                query = current.title
        
        if not query:
            await ctx.send("Please provide a song name or play something first.")
            return
        
        async with ctx.typing():
            lyrics = await self.lyrics_provider.search_lyrics(query)
        
        if not lyrics:
            await ctx.send(f"No lyrics found for '{query}'.")
            return
        
        # Split if too long
        chunks = [lyrics[i:i+4096] for i in range(0, len(lyrics), 4096)]
        
        for i, chunk in enumerate(chunks[:3], 1):
            embed = EmbedBuilder.lyrics(query, chunk, i, len(chunks))
            await ctx.send(embed=embed)
    
    @commands.command(name='stats', aliases=['botinfo', 'info'], help='Show bot statistics.')
    async def stats(self, ctx):
        uptime = format_duration(int(time.time() - self.start_time))
        total_queued = sum(len(self.queue_service.get_queue(g.id)) for g in self.bot.guilds)
        
        embed = EmbedBuilder.stats(
            uptime,
            len(self.bot.guilds),
            len(self.bot.voice_clients),
            total_queued,
            self.cache.get_all_stats()
        )
        await ctx.send(embed=embed)
    
    # --- 24/7 Mode ---
    
    @commands.has_permissions(manage_guild=True)
    @commands.command(name='247', aliases=['24/7', 'alwayson'], help='Toggle 24/7 mode.')
    async def toggle_247(self, ctx):
        guild_id = ctx.guild.id
        current = self.queue_service.get_247_mode(guild_id)
        new_state = not current
        self.queue_service.set_247_mode(guild_id, new_state)
        
        if new_state:
            await ctx.send("✅ **24/7 mode enabled** - I'll stay connected even when alone.")
        else:
            await ctx.send("❌ **24/7 mode disabled** - I'll disconnect when left alone.")
    
    # --- Auto-Play ---
    
    @commands.command(name='autoplay', aliases=['ap', 'radio'], help='Toggle auto-play recommendations.')
    async def toggle_autoplay(self, ctx):
        guild_id = ctx.guild.id
        current = self.queue_service.get_autoplay(guild_id)
        new_state = not current
        self.queue_service.set_autoplay(guild_id, new_state)
        
        if new_state:
            await ctx.send("🔄 **Auto-play enabled** - I'll play similar songs when the queue ends.")
        else:
            await ctx.send("⏹️ **Auto-play disabled** - I'll stop when the queue ends.")
    
    # --- Playlist Save/Load ---
    
    @commands.group(name='playlist', aliases=['pl'], invoke_without_command=True, help='Manage saved playlists.')
    async def playlist_cmd(self, ctx):
        """Show playlist help"""
        embed = discord.Embed(
            title="📋 Playlist Commands",
            description=(
                "`-playlist save <name>` - Save current queue\n"
                "`-playlist load <name>` - Load a saved playlist\n"
                "`-playlist list` - Show all saved playlists\n"
                "`-playlist delete <name>` - Delete a playlist"
            ),
            color=config.COLOR_INFO
        )
        await ctx.send(embed=embed)
    
    @playlist_cmd.command(name='save')
    async def playlist_save(self, ctx, *, name: str):
        """Save current queue as playlist"""
        guild_id = ctx.guild.id
        queue = self.queue_service.get_queue(guild_id)
        current = self.queue_service.get_current(guild_id)
        
        if not queue and not current:
            await ctx.send("❌ Queue is empty, nothing to save.")
            return
        
        count = self.queue_service.save_playlist(guild_id, name)
        await ctx.send(f"💾 Saved playlist **{name}** with {count} songs!")
    
    @playlist_cmd.command(name='load')
    async def playlist_load(self, ctx, *, name: str):
        """Load a saved playlist"""
        guild_id = ctx.guild.id
        songs = self.queue_service.load_playlist(guild_id, name)
        
        if not songs:
            await ctx.send(f"❌ Playlist **{name}** not found.")
            return
        
        count = self.queue_service.add_many(guild_id, songs)
        await ctx.send(f"📋 Loaded **{count}** songs from playlist **{name}**!")
        
        # Start playing if not already
        if not self.player.is_playing(guild_id) and not self.player.is_paused(guild_id):
            if ctx.author.voice:
                vc = ctx.voice_client or await self.player.connect(ctx.author.voice.channel)
                if vc:
                    success = await self.player.play_next(guild_id, self._after_play(guild_id))
                    if success:
                        current = self.queue_service.get_current(guild_id)
                        if current:
                            await self._send_now_playing(ctx, current)
    
    @playlist_cmd.command(name='list')
    async def playlist_list(self, ctx):
        """List all saved playlists"""
        playlists = self.queue_service.list_playlists(ctx.guild.id)
        
        if not playlists:
            await ctx.send("No saved playlists. Use `-playlist save <name>` to create one!")
            return
        
        embed = discord.Embed(
            title="📋 Saved Playlists",
            description="\n".join(f"• **{name}**" for name in playlists),
            color=config.COLOR_INFO
        )
        await ctx.send(embed=embed)
    
    @playlist_cmd.command(name='delete', aliases=['remove', 'del'])
    async def playlist_delete(self, ctx, *, name: str):
        """Delete a saved playlist"""
        if self.queue_service.delete_playlist(ctx.guild.id, name):
            await ctx.send(f"🗑️ Deleted playlist **{name}**.")
        else:
            await ctx.send(f"❌ Playlist **{name}** not found.")
    
    # --- Request Channel ---
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(name='requestchannel', aliases=['rc'], invoke_without_command=True, help='Set up song request channel.')
    async def requestchannel_cmd(self, ctx):
        """Show request channel status"""
        channel_id = self.queue_service.get_request_channel(ctx.guild.id)
        if channel_id:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                await ctx.send(f"🎵 Song requests are enabled in {channel.mention}")
            else:
                await ctx.send("⚠️ Request channel is set but channel no longer exists. Use `-requestchannel clear`")
        else:
            await ctx.send("Song request channel not set. Use `-requestchannel set` in the desired channel.")
    
    @requestchannel_cmd.command(name='set')
    async def requestchannel_set(self, ctx):
        """Set current channel as request channel"""
        self.queue_service.set_request_channel(ctx.guild.id, ctx.channel.id)
        await ctx.send(f"✅ Song requests enabled in {ctx.channel.mention}! Drop YouTube/Spotify links here.")
    
    @requestchannel_cmd.command(name='clear', aliases=['remove'])
    async def requestchannel_clear(self, ctx):
        """Clear request channel"""
        self.queue_service.set_request_channel(ctx.guild.id, None)
        await ctx.send("❌ Song request channel disabled.")
    
    # --- Request Channel Listener ---
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for URLs in request channel"""
        if message.author.bot or not message.guild:
            return
        
        request_channel_id = self.queue_service.get_request_channel(message.guild.id)
        if not request_channel_id or message.channel.id != request_channel_id:
            return
        
        # Check for URLs
        import re
        url_pattern = re.compile(r'https?://[^\s]+')
        urls = url_pattern.findall(message.content)
        
        if not urls:
            return
        
        # Check for YouTube or Spotify URLs
        valid_url = None
        for url in urls:
            if 'youtube.com' in url or 'youtu.be' in url or 'spotify.com' in url:
                valid_url = url
                break
        
        if not valid_url:
            return
        
        # Check if user is in voice
        if not message.author.voice:
            await message.add_reaction('❌')
            return
        
        guild_id = message.guild.id
        
        # Connect if needed
        vc = message.guild.voice_client
        if not vc:
            vc = await self.player.connect(message.author.voice.channel)
            if not vc:
                await message.add_reaction('❌')
                return
        
        # Extract and queue
        results = await self.extractor.extract(valid_url, message.author)
        
        if isinstance(results, dict) and 'error' in results:
            await message.add_reaction('❌')
            return
        
        if not results:
            await message.add_reaction('❌')
            return
        
        # Add to queue
        if len(results) == 1:
            self.queue_service.add(guild_id, results[0])
            await message.add_reaction('✅')
        else:
            self.queue_service.add_many(guild_id, results)
            await message.add_reaction('📋')  # Playlist indicator
        
        # Start playing if not already
        if not self.player.is_playing(guild_id) and not self.player.is_paused(guild_id):
            # Create a fake ctx for now playing
            ctx = await self.bot.get_context(message)
            success = await self.player.play_next(guild_id, self._after_play(guild_id))
            if success:
                current = self.queue_service.get_current(guild_id)
                if current:
                    await self._send_now_playing(ctx, current)


async def setup(bot):
    """Load the music cog"""
    await bot.add_cog(MusicCommands(bot))
    logger.info("Music Commands loaded")
