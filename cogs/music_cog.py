# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
import datetime
import re
import random
import time

# Import config and utilities
import config
from utils.helpers import format_duration, parse_time, create_progress_bar, format_time_until, calculate_total_queue_duration
from utils.cache import GuildCache
from utils.lyrics import LyricsProvider

# --- FFmpeg and yt-dlp Options ---
# Use config options
PLAYLIST_URL_PATTERN = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(playlist)\?(list=.*)$')

# --- Helper Functions ---
# No longer needed here - using imports from utils.helpers

# --- Music Control View (Updated with Shuffle Button) ---
class MusicControlView(discord.ui.View):
    # (Keep the entire MusicControlView class exactly as it was in the previous correct version)
    def __init__(self, cog_ref, timeout=None):
        super().__init__(timeout=timeout)
        self.cog = cog_ref
        self.message = None
        self.ctx_ref = None
        self.interaction = None

    def _get_vc(self):
        # (Keep _get_vc as corrected before)
        if self.cog and self.cog.bot.guilds:
             target_guild = None
             if self.interaction and self.interaction.guild: target_guild = self.interaction.guild
             elif self.message and self.message.guild: target_guild = self.message.guild
             elif self.ctx_ref and self.ctx_ref.guild: target_guild = self.ctx_ref.guild # Added fallback to ctx_ref
             if target_guild: return discord.utils.get(self.cog.bot.voice_clients, guild=target_guild)
        return None

    def update_buttons(self, interaction: discord.Interaction = None):
        # (Keep update_buttons as corrected before, including loop button style)
        if interaction: self.interaction = interaction
        target_guild: discord.Guild = None
        if self.interaction and self.interaction.guild: target_guild = self.interaction.guild
        elif self.message and self.message.guild: target_guild = self.message.guild
        elif self.ctx_ref and self.ctx_ref.guild: target_guild = self.ctx_ref.guild # Added fallback to ctx_ref
        if not target_guild: self.cog.logger.warning("update_buttons no guild context."); return
        guild_id = target_guild.id
        vc = discord.utils.get(self.cog.bot.voice_clients, guild=target_guild)

        loop_mode = self.cog.loop_mode.get(guild_id, 'off')

        pause_resume_button = discord.utils.get(self.children, custom_id="pause_resume")
        loop_button = discord.utils.get(self.children, custom_id="loop")
        shuffle_button = discord.utils.get(self.children, custom_id="shuffle")

        is_paused = vc and vc.is_paused(); is_playing = vc and vc.is_playing()
        if pause_resume_button:
            if is_paused: pause_resume_button.emoji = "▶️"; pause_resume_button.style = discord.ButtonStyle.success; pause_resume_button.disabled = False
            elif is_playing: pause_resume_button.emoji = "⏸️"; pause_resume_button.style = discord.ButtonStyle.primary; pause_resume_button.disabled = False
            else: pause_resume_button.emoji = "⏸️"; pause_resume_button.style = discord.ButtonStyle.secondary; pause_resume_button.disabled = True

        if loop_button:
             if loop_mode == 'song':
                 loop_button.emoji = '🔂'; loop_button.style = discord.ButtonStyle.success
             elif loop_mode == 'queue':
                 loop_button.emoji = '🔁'; loop_button.style = discord.ButtonStyle.success
             else: # Off
                 loop_button.emoji = '🔁'; loop_button.style = discord.ButtonStyle.secondary

        if shuffle_button:
            queue = self.cog.queues.get(guild_id, [])
            shuffle_button.disabled = len(queue) < 2


    async def edit_message_with_updated_view(self, interaction: discord.Interaction = None):
        # (Keep edit_message_with_updated_view as before)
         if self.message:
            try: self.update_buttons(interaction); await self.message.edit(view=self)
            except discord.NotFound: self.stop()
            except discord.HTTPException as e: self.cog.logger.warning(f"Failed edit NP {self.message.id}: {e}")

    # --- Button Callbacks ---
    # (Keep all button callbacks: pause_resume, skip, loop, shuffle, queue, clear, leave exactly the same)
    # Row 0: Pause/Resume, Skip, Loop, Shuffle
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary, custom_id="pause_resume", row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction; vc = self._get_vc()
        if not vc: await interaction.response.send_message("Not connected.", ephemeral=True, delete_after=10); return
        if vc.is_playing(): vc.pause(); await interaction.response.send_message("Paused.", ephemeral=True, delete_after=10)
        elif vc.is_paused(): vc.resume(); await interaction.response.send_message("Resumed.", ephemeral=True, delete_after=10)
        else: await interaction.response.send_message("Nothing playing.", ephemeral=True, delete_after=10)
        await self.edit_message_with_updated_view(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction; vc = self._get_vc()
        if vc and (vc.is_playing() or vc.is_paused()): await interaction.response.send_message("Skipping...", ephemeral=True, delete_after=5); vc.stop()
        else: await interaction.response.send_message("Nothing to skip.", ephemeral=True, delete_after=10)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop", row=0)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction; guild_id = interaction.guild_id
        current_mode = self.cog.loop_mode.get(guild_id, 'off')
        if current_mode == 'off': new_mode = 'song'
        elif current_mode == 'song': new_mode = 'queue'
        else: new_mode = 'off'
        self.cog.loop_mode[guild_id] = new_mode
        mode_text = "Song Loop" if new_mode == 'song' else "Queue Loop" if new_mode == 'queue' else "Loop Off"
        await interaction.response.send_message(f"{mode_text} enabled.", ephemeral=True, delete_after=10)
        await self.edit_message_with_updated_view(interaction)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle", row=0)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction
        guild_id = interaction.guild_id
        if guild_id not in self.cog.queues or len(self.cog.queues[guild_id]) < 2:
            await interaction.response.send_message("Not enough songs in the queue to shuffle.", ephemeral=True, delete_after=10)
            return
        random.shuffle(self.cog.queues[guild_id])
        await interaction.response.send_message("🔀 Queue shuffled!", ephemeral=True, delete_after=10)
        # Optionally update the queue view if open? Or just leave as is.
        # await self.edit_message_with_updated_view(interaction) # Might not be needed

    # --- Row 1: Queue, Clear, Leave ---
    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="queue", row=1)
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction
        guild_id = interaction.guild_id; embed = discord.Embed(title="🎵 Song Queue 🎵", color=discord.Color.blue())
        np_info = self.cog.current_song.get(guild_id); q = self.cog.queues.get(guild_id, [])
        if np_info: embed.add_field(name="▶️ Now Playing", value=f"**{np_info['title']}** (Req by {np_info['requester'].mention})", inline=False)
        else: embed.add_field(name="▶️ Now Playing", value="Nothing playing.", inline=False)
        if q:
            queue_list = ""; limit = 10
            for i, song in enumerate(q[:limit]): queue_list += f"{i+1}. **{song['title']}** (Req by {song['requester'].display_name})\n"
            embed.add_field(name=f"Up Next ({len(q)} total)", value=queue_list.strip() or "Empty", inline=False)
            if len(q) > limit: embed.set_footer(text=f"...and {len(q) - limit} more.")
        else: embed.add_field(name="Up Next", value="The queue is empty!", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🗑️", label="Clear", style=discord.ButtonStyle.danger, custom_id="clear", row=1)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction
        guild_id = interaction.guild_id
        if guild_id in self.cog.queues and self.cog.queues[guild_id]: count = len(self.cog.queues[guild_id]); self.cog.queues[guild_id] = []; await interaction.response.send_message(f"Cleared {count} songs.", ephemeral=True, delete_after=10)
        else: await interaction.response.send_message("Queue empty.", ephemeral=True, delete_after=10)

    @discord.ui.button(emoji="🚪", label="Leave", style=discord.ButtonStyle.danger, custom_id="leave", row=1)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.interaction = interaction; vc = self._get_vc()
        if vc: await interaction.response.send_message("Leaving...", ephemeral=True, delete_after=5); await vc.disconnect(force=True)
        else: await interaction.response.send_message("Not connected.", ephemeral=True, delete_after=10)

# --- Queue Pagination View ---
class QueuePaginationView(discord.ui.View):
    def __init__(self, cog, guild_id, pages, timeout=60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.pages = pages
        self.current_page = 0
        self.message = None
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

# --- Music Cog Class ---
class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.queues = {}
        self.current_song = {}
        self.loop_mode = {} # Modes: 'off', 'song', 'queue'
        self.now_playing_messages = {}
        
        # NEW: Add caching, lyrics, and additional features
        self.cache = GuildCache(max_size=config.MAX_CACHE_SIZE)
        self.lyrics_provider = LyricsProvider(config.LYRICS_API_URL)
        self.volume_settings = {}  # guild_id: volume (0-100)
        self.playback_history = {}  # guild_id: list of songs (max 50)
        self.audio_effects = {}  # guild_id: {speed: float, bass_boost: str}
        self.start_time = time.time()  # For uptime tracking
        self.song_start_times = {}  # guild_id: timestamp when song started
        self.vote_skip_voters = {}  # guild_id: set of user_ids
        
        # Start cache cleanup task
        self.cache_cleanup_task = self.bot.loop.create_task(self.cache_cleanup_loop())
    
    async def cache_cleanup_loop(self):
        """Periodic task to cleanup expired cache items"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self.cache.cleanup_all()
                self.logger.info("Cache cleanup completed")
            except Exception as e:
                self.logger.error(f"Error in cache cleanup: {e}", exc_info=True)
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if hasattr(self, 'cache_cleanup_task'):
            self.cache_cleanup_task.cancel()

    # --- Helper Methods ---
    # (delete_now_playing_message, send_now_playing, resolve_stream_url, search_and_get_info remain the same)
    async def delete_now_playing_message(self, guild_id):
        # (Same as before)
        if guild_id in self.now_playing_messages:
            message = self.now_playing_messages.pop(guild_id);
            try:
                 # Make sure view is stopped before deleting message if possible
                 view = discord.ui.View.from_message(message)
                 if view: view.stop()
                 await message.delete()
            except discord.NotFound: pass # Message already gone
            except Exception as e: self.logger.warning(f"Error deleting/stopping view for NP G:{guild_id}: {e}")


    async def send_now_playing(self, ctx, song_to_play, view_instance):
        """Send enhanced now playing message with progress bar and metadata"""
        guild_id = ctx.guild.id
        requester = song_to_play['requester']
        await self.delete_now_playing_message(guild_id) # Clear old message first
        
        # Create embed with enhanced info
        embed = discord.Embed(
            title=song_to_play['title'],
            url=song_to_play.get('webpage_url'),
            color=config.COLOR_PLAYING
        )
        embed.set_author(name=f"Requested by {requester.display_name}", icon_url=requester.display_avatar.url)
        
        # Duration and uploader
        duration = song_to_play.get('duration')
        embed.add_field(name="Duration", value=format_duration(duration), inline=True)
        embed.add_field(name="Uploader", value=song_to_play.get('uploader', 'N/A'), inline=True)
        
        # Volume and effects
        volume = self.volume_settings.get(guild_id, config.DEFAULT_VOLUME)
        embed.add_field(name="Volume", value=f"{volume}%", inline=True)
        
        # Queue info
        queue_len = len(self.queues.get(guild_id, []))
        if queue_len > 0:
            embed.add_field(name="In Queue", value=f"{queue_len} songs", inline=True)
        
        # Loop mode
        loop_mode = self.loop_mode.get(guild_id, 'off')
        if loop_mode == 'song':
            embed.add_field(name="Loop", value="🔂 Song", inline=True)
        elif loop_mode == 'queue':
            embed.add_field(name="Loop", value="🔁 Queue", inline=True)
        
        if song_to_play.get('thumbnail'):
            embed.set_thumbnail(url=song_to_play.get('thumbnail'))
        
        embed.set_footer(text="Now Playing 🎵")
        
        try:
            view_instance.ctx_ref = ctx # Store context ref
            view_instance.update_buttons() # Update buttons before sending
            message = await ctx.send(embed=embed, view=view_instance)
            self.now_playing_messages[guild_id] = message
            view_instance.message = message # Link message to view AFTER sending
        except discord.HTTPException as e:
            self.logger.error(f"Failed send NP msg G:{guild_id}: {e}")
            view_instance.stop() # Stop the view if sending failed

    async def resolve_stream_url(self, video_id_or_url: str):
        # Check cache first
        cache_key = f"stream:{video_id_or_url}"
        cached_url = await self.cache.stream_url_cache.get(cache_key)
        if cached_url:
            self.logger.info(f"Cache hit for stream: {video_id_or_url}")
            return cached_url
        
        # Original resolution logic
        self.logger.info(f"Resolving stream URL for: {video_id_or_url}")
        ydl_opts = config.YDL_BASE_OPTIONS.copy(); ydl_opts['extract_flat'] = False; loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: data = await loop.run_in_executor(None, lambda: ydl.extract_info(video_id_or_url, download=False))
            if not data: return None
            stream_url = data.get('url');
            if stream_url and data.get('acodec') != 'none':
                # Cache the result
                await self.cache.stream_url_cache.set(cache_key, stream_url, config.STREAM_URL_CACHE_TTL)
                return stream_url
            for fmt in data.get('formats', []):
                if fmt.get('acodec') == 'opus' and fmt.get('url'):
                    stream_url = fmt['url']
                    await self.cache.stream_url_cache.set(cache_key, stream_url, config.STREAM_URL_CACHE_TTL)
                    return stream_url
            for fmt in data.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none' and fmt.get('url'):
                    stream_url = fmt['url']
                    await self.cache.stream_url_cache.set(cache_key, stream_url, config.STREAM_URL_CACHE_TTL)
                    return stream_url
            self.logger.warning(f"No audio stream URL found for {video_id_or_url} after resolution."); return None
        except Exception as e: self.logger.error(f"Error resolving stream URL {video_id_or_url}: {e}", exc_info=True); return None

    async def search_and_get_info(self, query: str):
        # Check cache first
        cache_key = f"search:{query}"
        cached_result = await self.cache.metadata_cache.get(cache_key)
        if cached_result:
            self.logger.info(f"Cache hit for search: {query}")
            return cached_result
        
        # Original search logic
        is_playlist = bool(PLAYLIST_URL_PATTERN.match(query)); ydl_opts = config.YDL_BASE_OPTIONS.copy()
        if is_playlist: self.logger.info(f"Playlist detected: {query}"); ydl_opts['extract_flat'] = True; ydl_opts['noplaylist'] = False
        else: self.logger.info(f"Single/Search: {query}"); ydl_opts['extract_flat'] = False; ydl_opts['noplaylist'] = True
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: data = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            if not data: return {'error': 'yt-dlp returned no data.'}
            entries_to_process = data['entries'] if 'entries' in data and data['entries'] else [data] if isinstance(data, dict) and 'entries' not in data else []
            if not entries_to_process: return {'error': 'Playlist/Search yielded no results.'}
            songs_list = []
            for entry in entries_to_process:
                if not entry: continue
                resolved_url = entry.get('url') if not is_playlist else None; video_id = entry.get('id')
                if not video_id: self.logger.warning(f"Skipping entry missing ID: {entry.get('title', 'N/A')}"); continue
                songs_list.append({'id': video_id, 'title': entry.get('title', 'Unknown Title'), 'url': resolved_url,
                                   'resolved': resolved_url is not None and not entry.get('url', '').startswith(('http://www.youtube.com','https://www.youtube.com')),
                                   'duration': entry.get('duration'), 'thumbnail': entry.get('thumbnail'), 'uploader': entry.get('uploader'),
                                   'webpage_url': entry.get('webpage_url', f"https://www.youtube.com/watch?v={video_id}")})
            
            # Cache the result
            if songs_list:
                await self.cache.metadata_cache.set(cache_key, songs_list, config.METADATA_CACHE_TTL)
            
            return songs_list
        except yt_dlp.utils.DownloadError as e: self.logger.error(f"yt-dlp DownloadError '{query}': {e}", exc_info=True); return {'error': f"yt-dlp error: {e}"} # Simplified error
        except Exception as e: self.logger.error(f"search_and_get_info error '{query}': {e}", exc_info=True); return {'error': f"Unexpected error: {e}"}

    # --- Play Next Logic ---
    async def play_next_async(self, ctx):
        # (play_next_async remains largely the same as the previous correct version)
        # It correctly creates a NEW view instance for each song.
        guild_id = ctx.guild.id
        vc = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not vc or not vc.is_connected():
            self.logger.warning(f"play_next_async: VC invalid G:{guild_id}.")
            await self.delete_now_playing_message(guild_id)
            if guild_id in self.current_song: del self.current_song[guild_id]
            return

        # --- Queue Looping Logic ---
        current_mode = self.loop_mode.get(guild_id, 'off')
        finished_song_info = self.current_song.get(guild_id)
        if current_mode == 'queue' and finished_song_info:
            if finished_song_info.get('id') and finished_song_info.get('title'):
                 song_copy = finished_song_info.copy()
                 song_copy['resolved'] = False; song_copy['url'] = None
                 if guild_id not in self.queues: self.queues[guild_id] = []
                 self.queues[guild_id].append(song_copy)
                 self.logger.info(f"Looping queue: Re-added '{song_copy['title']}' G:{guild_id}")
            else:
                 self.logger.warning(f"Cannot loop queue for song missing id/title G:{guild_id}")

        song_to_play = None
        # --- Determine Song ---
        if current_mode == 'song' and finished_song_info:
            song_to_play = finished_song_info.copy()
            song_to_play['resolved'] = song_to_play.get('url') is not None and song_to_play.get('resolved', False)
        elif guild_id in self.queues and self.queues[guild_id]:
            song_to_play = self.queues[guild_id].pop(0)
            self.current_song[guild_id] = song_to_play
        else: # Queue empty
            if guild_id in self.current_song: del self.current_song[guild_id]
            # Important: Stop the view of the *last* song if the queue is now empty
            await self.delete_now_playing_message(guild_id)
            # Optional: Send "Queue finished" message
            # try: await ctx.send("⏹️ Queue finished.", delete_after=30)
            # except: pass # Ignore if ctx is somehow invalid
            return # Stop playback

        if not song_to_play:
            self.logger.error(f"play_next_async: No song determined G:{guild_id}")
            return

        # --- Resolve Stream URL if Needed ---
        if not song_to_play.get('resolved', False) or not song_to_play.get('url'):
            video_id = song_to_play.get('id')
            if not video_id: self.logger.error(f"Missing ID: {song_to_play.get('title')}"); await ctx.send(f"❌ Skipping '{song_to_play.get('title', 'Unknown')}' (Missing ID)."); self.play_next(ctx); return
            loading_msg = None
            try: loading_msg = await ctx.send(f"⏳ Loading **{song_to_play['title']}**...");
            except discord.HTTPException: pass # Ignore if channel interactions are disabled etc.
            resolved_url = await self.resolve_stream_url(video_id)
            if loading_msg:
                try: await loading_msg.delete()
                except: pass
            if not resolved_url: await ctx.send(f"❌ Failed stream for **{song_to_play['title']}**. Skipping."); self.logger.warning(f"Failed resolve ID {video_id}. Skipping."); self.play_next(ctx); return
            else:
                song_to_play['url'] = resolved_url; song_to_play['resolved'] = True
                if guild_id in self.current_song and self.current_song[guild_id].get('id') == video_id:
                    self.current_song[guild_id]['url'] = resolved_url; self.current_song[guild_id]['resolved'] = True

        # --- Play the Song ---
        title = song_to_play['title']; stream_url = song_to_play['url']
        try:
            if not isinstance(stream_url, str) or not stream_url.startswith('http'): raise ValueError(f"Invalid stream URL: {stream_url}")
            
            # Get volume and effects for this guild
            volume = self.volume_settings.get(guild_id, config.DEFAULT_VOLUME)
            effects = self.audio_effects.get(guild_id, {'speed': 1.0, 'bass_boost': 'off'})
            
            # Generate FFmpeg options with dynamic filters
            ffmpeg_opts = config.get_ffmpeg_options(
                volume=volume,
                speed=effects['speed'],
                bass_boost=effects['bass_boost']
            )
            
            source = discord.FFmpegOpusAudio(stream_url, **ffmpeg_opts)
            
            # Track start time for progress tracking
            self.song_start_times[guild_id] = time.time()
            
            # Add to playback history
            if guild_id not in self.playback_history:
                self.playback_history[guild_id] = []
            self.playback_history[guild_id].append(song_to_play.copy())
            if len(self.playback_history[guild_id]) > config.MAX_HISTORY_SIZE:
                self.playback_history[guild_id].pop(0)
            
            # Create a NEW view instance for EACH song
            view = MusicControlView(self)
            vc.play(source, after=lambda e: self.after_play_handler(e, ctx))
            # Send the now playing embed with the new view
            await self.send_now_playing(ctx, song_to_play, view)
        except ValueError as ve: self.logger.error(f"Value error playback '{title}' G:{guild_id}: {ve}"); await ctx.send(f"❌ Error playing **{title}**: Invalid data."); self.play_next(ctx)
        except Exception as e: self.logger.error(f"Playback error '{title}' G:{guild_id}: {e}", exc_info=True); await ctx.send(f"❌ Error playing **{title}**: {e}"); self.play_next(ctx)


    # --- Sync Wrapper for play_next_async ---
    def play_next(self, ctx):
        # This function is called from various places (commands, after_play_handler)
        # It ensures play_next_async runs in the bot's main event loop
        asyncio.run_coroutine_threadsafe(self.play_next_async(ctx), self.bot.loop)

    # --- NEW: Async helper for view cleanup ---
    async def _cleanup_view_async(self, guild_id):
        """Safely stops the view associated with the finished song."""
        if guild_id in self.now_playing_messages:
            message = self.now_playing_messages.get(guild_id) # Use .get for safety
            if message:
                try:
                    # Getting view from message might still need the loop,
                    # but stopping it definitely does.
                    view = discord.ui.View.from_message(message)
                    if view and isinstance(view, MusicControlView):
                        self.logger.info(f"Stopping view for NP msg {message.id} G:{guild_id}")
                        view.stop()
                    # We don't delete the message here, delete_now_playing_message handles that
                    # when the *next* song starts or the bot stops/leaves.
                except discord.NotFound:
                    self.logger.warning(f"NP message {message.id} not found for cleanup G:{guild_id}")
                    # Remove potentially stale entry if message is gone
                    if guild_id in self.now_playing_messages and self.now_playing_messages[guild_id].id == message.id:
                         del self.now_playing_messages[guild_id]
                except Exception as e:
                    self.logger.error(f"Error stopping view for NP msg {message.id} G:{guild_id}: {e}", exc_info=True)

    # --- MODIFIED: after_play_handler ---
    def after_play_handler(self, error, ctx):
        """Callback after a song finishes or is stopped. MUST be threadsafe."""
        guild_id = ctx.guild.id if ctx.guild else 'DM' # Getting guild ID is safe

        # Logging the error is safe
        if error:
            # Avoid accessing current_song directly if it might be modified elsewhere concurrently
            # It's generally safer to log just the error here.
            self.logger.error(f"Player error G:{guild_id}: {error}", exc_info=error)

        # --- Schedule view cleanup on the main loop ---
        # Check if guild_id exists before scheduling
        if guild_id in self.now_playing_messages:
             asyncio.run_coroutine_threadsafe(self._cleanup_view_async(guild_id), self.bot.loop)
        # --- End Scheduling ---

        # --- Trigger the next action (play next song) ---
        # This already uses run_coroutine_threadsafe internally via play_next->play_next_async
        self.play_next(ctx)


    # --- Listeners ---
    # (on_voice_state_update remains the same)
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Bot disconnects
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            self.logger.info(f"Bot disconnected VC G:{guild_id}")
            if guild_id in self.queues: self.queues[guild_id].clear()
            if guild_id in self.current_song: del self.current_song[guild_id]
            if guild_id in self.loop_mode: del self.loop_mode[guild_id]
            await self.delete_now_playing_message(guild_id) # Ensure NP message/view is cleaned up
            return

        # Auto-disconnect if bot is alone
        if not member.bot and before.channel:
             # Check if the channel still exists and has members
            if before.channel.guild: # Ensure channel is not None and has a guild
                vc = discord.utils.get(self.bot.voice_clients, guild=before.channel.guild)
                # Check if bot is connected, in the *same channel* user left, and now alone
                if vc and vc.channel == before.channel and len(vc.channel.members) == 1 and self.bot.user in vc.channel.members:
                    await asyncio.sleep(120) # Wait 2 minutes
                    # Recheck conditions *after* waiting
                    vc_still_present = discord.utils.get(self.bot.voice_clients, guild=before.channel.guild)
                    if vc_still_present and vc_still_present.channel == before.channel and len(vc_still_present.channel.members) == 1:
                        guild_id = before.channel.guild.id
                        self.logger.info(f"Bot alone G:{guild_id} after delay, disconnecting.")
                        await vc_still_present.disconnect(force=True) # Disconnect


    # --- Commands ---
    # (All commands: join, leave, play, remove, shuffle, loop, pause, resume, stop, skip, queue, np, clear remain the same as the previous correct version)
    @commands.command(name='join', help='Makes the bot join your current voice channel.')
    async def join(self, ctx):
        if not ctx.author.voice: await ctx.send("You're not in a VC."); return
        vc = ctx.voice_client
        target_channel = ctx.author.voice.channel
        if vc and vc.channel == target_channel: await ctx.message.add_reaction('👌'); return
        try:
            if vc: await vc.move_to(target_channel)
            else: await target_channel.connect(timeout=30.0, reconnect=True)
            await ctx.message.add_reaction('✅')
        except asyncio.TimeoutError: await ctx.send(f"Timeout {'moving to' if vc else 'connecting to'} {target_channel.mention}.")
        except Exception as e: await ctx.send(f"Error {'moving' if vc else 'joining'}: {e}")

    @commands.command(name='leave', aliases=['disconnect', 'dc'], help='Makes the bot leave the voice channel.')
    async def leave(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_connected():
            await ctx.message.add_reaction('👋');
            # Ensure cleanup happens before disconnect potentially triggers on_voice_state_update
            guild_id = ctx.guild.id
            if guild_id in self.loop_mode: del self.loop_mode[guild_id]
            if guild_id in self.queues: self.queues[guild_id] = []
            if guild_id in self.current_song: del self.current_song[guild_id]
            await self.delete_now_playing_message(guild_id) # Stop view and delete message
            await vc.disconnect(force=True)
        else: await ctx.send("Not in VC.", delete_after=10); await ctx.message.add_reaction('❓')

    @commands.command(name='play', aliases=['p'], help='Plays song/playlist or adds to queue.')
    async def play(self, ctx, *, query: str):
        # (VC Handling Logic - Same as before)
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You need to be in a voice channel first!")
            return
        vc = ctx.voice_client
        target_channel = ctx.author.voice.channel
        if not vc:
            try: vc = await target_channel.connect(timeout=30.0, reconnect=True)
            except asyncio.TimeoutError: await ctx.send(f"Timeout connecting to {target_channel.mention}."); return
            except Exception as e: await ctx.send(f"Error connecting: {e}"); self.logger.error(f"Connection error G:{ctx.guild.id}: {e}", exc_info=True); return
        elif vc.channel != target_channel:
            try: await vc.move_to(target_channel)
            except asyncio.TimeoutError: await ctx.send(f"Timeout moving to {target_channel.mention}."); return
            except Exception as e: await ctx.send(f"Error moving: {e}"); self.logger.error(f"Move error G:{ctx.guild.id}: {e}", exc_info=True); return

        # (Search and Queueing Logic - With validation)
        guild_id = ctx.guild.id
        results = None
        async with ctx.typing(): results = await self.search_and_get_info(query)
        if not results: await ctx.send(f"❌ No results found for '{query}'."); return
        if isinstance(results, dict) and 'error' in results: await ctx.send(f"❌ Error: {results['error']}"); return
        if not isinstance(results, list): await ctx.send(f"❌ Unexpected error processing results."); self.logger.error(f"search_and_get_info returned non-list/dict: {results}"); return
        if guild_id not in self.queues: self.queues[guild_id] = []
        
        # Validate queue size limit
        current_queue_size = len(self.queues[guild_id])
        if config.MAX_QUEUE_SIZE > 0 and current_queue_size >= config.MAX_QUEUE_SIZE:
            await ctx.send(f"❌ Queue is full! Maximum size is {config.MAX_QUEUE_SIZE} songs.", delete_after=15)
            return
        
        is_playing_or_paused = vc.is_playing() or vc.is_paused()
        start_playing = not is_playing_or_paused; added_count = 0; skipped_count = 0
        
        for song_info in results:
            # Check queue size limit
            if config.MAX_QUEUE_SIZE > 0 and len(self.queues[guild_id]) >= config.MAX_QUEUE_SIZE:
                skipped_count = len(results) - added_count
                break
            
            # Check song duration limit
            duration = song_info.get('duration')
            if config.MAX_SONG_DURATION > 0 and duration and duration > config.MAX_SONG_DURATION:
                self.logger.info(f"Skipping song '{song_info.get('title')}' - exceeds max duration ({duration}s > {config.MAX_SONG_DURATION}s)")
                skipped_count += 1
                continue
            
            song_info['requester'] = ctx.author
            self.queues[guild_id].append(song_info)
            added_count += 1
        
        if added_count == 0:
            if skipped_count > 0:
                await ctx.send(f"❌ All {skipped_count} songs exceeded the maximum duration of {format_duration(config.MAX_SONG_DURATION)}.")
            else:
                await ctx.send(f"❌ No valid songs found or added for '{query}'.")
            return
        
        first_title = results[0].get('title', 'Unknown Title') # Safer access
        queue_len = len(self.queues[guild_id])
        
        # Send feedback
        if added_count == 1:
            if start_playing: await ctx.message.add_reaction('🎶') # Indicate starting playback
            else: await ctx.send(f"✅ Added **{first_title}** to queue (#{queue_len}).")
        else:
            message = f"✅ Added **{added_count}** songs to queue (starting with **{first_title}**)."
            if skipped_count > 0:
                message += f"\n⚠️ Skipped {skipped_count} songs (too long or queue full)."
            await ctx.send(message)
            if start_playing: await ctx.message.add_reaction('🎶') # Indicate starting playback
        
        if start_playing:
            self.play_next(ctx) # Start playback cycle

    @commands.command(name='remove', aliases=['rm'], help='Removes a song from the queue by its index.')
    async def remove(self, ctx, index: int):
        guild_id = ctx.guild.id
        if guild_id not in self.queues or not self.queues[guild_id]:
            await ctx.send("The queue is empty.", delete_after=10); await ctx.message.add_reaction('❓'); return
        queue_len = len(self.queues[guild_id])
        if not 1 <= index <= queue_len:
            await ctx.send(f"Invalid index. Must be between 1 and {queue_len}.", delete_after=10); await ctx.message.add_reaction('❌'); return
        removed_song = self.queues[guild_id].pop(index - 1)
        await ctx.send(f"🗑️ Removed **{removed_song.get('title','Unknown Title')}** (position {index}).")
        await ctx.message.add_reaction('✅')

    @commands.command(name='shuffle', help='Shuffles the current song queue.')
    async def shuffle(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.queues or len(self.queues[guild_id]) < 2:
            await ctx.send("Not enough songs in the queue to shuffle.", delete_after=10); await ctx.message.add_reaction('❓'); return
        random.shuffle(self.queues[guild_id])
        await ctx.send("🔀 Queue shuffled!")
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop', help='Cycles loop modes: off -> song -> queue -> off.')
    async def loop(self, ctx):
        guild_id = ctx.guild.id
        current_mode = self.loop_mode.get(guild_id, 'off')
        if current_mode == 'off': new_mode = 'song'
        elif current_mode == 'song': new_mode = 'queue'
        else: new_mode = 'off'
        self.loop_mode[guild_id] = new_mode
        mode_text = "Song Loop 🔂" if new_mode == 'song' else "Queue Loop 🔁" if new_mode == 'queue' else "Loop Off 🚫"
        await ctx.send(f"Loop mode set to: **{mode_text}**")
        await ctx.message.add_reaction('✅')
        # Update the NP message view if it exists
        if guild_id in self.now_playing_messages:
             message = self.now_playing_messages.get(guild_id)
             if message:
                view = discord.ui.View.from_message(message)
                if view and isinstance(view, MusicControlView):
                    try:
                        view.update_buttons() # Update internal state based on new loop mode
                        await message.edit(view=view) # Edit the message with updated button appearance
                    except Exception as e:
                        self.logger.warning(f"Failed auto-update NP view on loop command G:{guild_id}: {e}")

    @commands.command(name='pause', help='Pauses the currently playing song.')
    @commands.has_permissions(manage_messages=True) # Or adjust perms as needed
    async def pause(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing(): vc.pause(); await ctx.message.add_reaction('⏸️')
        else: await ctx.send("Not playing or already paused.", delete_after=10); await ctx.message.add_reaction('❓')

    @commands.command(name='resume', aliases=['unpause'], help='Resumes paused playback.')
    @commands.has_permissions(manage_messages=True) # Or adjust perms as needed
    async def resume(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_paused(): vc.resume(); await ctx.message.add_reaction('▶️')
        else: await ctx.send("Nothing to resume.", delete_after=10); await ctx.message.add_reaction('❓')

    @commands.command(name='stop', help='Stops playback and clears the queue.')
    @commands.has_permissions(manage_messages=True) # Or adjust perms as needed
    async def stop(self, ctx):
        vc = ctx.voice_client; guild_id = ctx.guild.id
        if vc and (vc.is_playing() or vc.is_paused()):
            self.logger.info(f"Stop command called G:{guild_id}")
            # Clear state *before* stopping VC, as stop triggers 'after'
            if guild_id in self.queues: self.queues[guild_id] = []
            if guild_id in self.current_song: del self.current_song[guild_id]
            if guild_id in self.loop_mode: del self.loop_mode[guild_id]
            await self.delete_now_playing_message(guild_id) # Stop view and delete message
            vc.stop() # Let after_play_handler run (it will find queue empty and stop)
            await ctx.message.add_reaction('⏹️')
        else: await ctx.send("Not playing.", delete_after=10); await ctx.message.add_reaction('❓')

    @commands.command(name='skip', aliases=['s'], help='Skips the current song.')
    @commands.has_permissions(manage_messages=True) # Or adjust perms as needed
    async def skip(self, ctx):
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
             await ctx.message.add_reaction('⏭️')
             vc.stop() # Triggers after_play_handler -> _cleanup_view_async -> play_next
        else: await ctx.send("Nothing to skip.", delete_after=10); await ctx.message.add_reaction('❓')

    @commands.command(name='queue', aliases=['q'], help='Shows the current song queue.')
    async def queue(self, ctx):
        """Display queue with pagination and enhanced info"""
        guild_id = ctx.guild.id
        np_info = self.current_song.get(guild_id)
        q = self.queues.get(guild_id, [])
        loop_mode = self.loop_mode.get(guild_id, 'off')
        
        # Calculate current song progress if playing
        current_progress = ""
        if np_info and guild_id in self.song_start_times:
            elapsed = int(time.time() - self.song_start_times[guild_id])
            duration = np_info.get('duration', 0)
            if duration:
                progress_bar = create_progress_bar(elapsed, duration, length=15)
                current_progress = f"\n{progress_bar} {format_duration(elapsed)}/{format_duration(duration)}"
        
        # Build pages (10 songs per page)
        songs_per_page = 10
        pages = []
        
        # First page with now playing
        embed = discord.Embed(title="🎵 Song Queue 🎵", color=config.COLOR_QUEUED)
        
        if np_info:
            np_value = f"**{np_info['title']}**\nRequested by {np_info['requester'].mention}{current_progress}"
            embed.add_field(name="▶️ Now Playing", value=np_value, inline=False)
        else:
            embed.add_field(name="▶️ Now Playing", value="Nothing playing.", inline=False)
        
        if not q:
            embed.add_field(name="Up Next", value="The queue is empty!", inline=False)
            footer_text = ""
            if loop_mode == 'song':
                footer_text = "Loop: Song 🔂"
            elif loop_mode == 'queue':
                footer_text = "Loop: Queue 🔁"
            if footer_text:
                embed.set_footer(text=footer_text)
            await ctx.send(embed=embed)
            return
        
        # Add queue songs with pagination
        total_duration = calculate_total_queue_duration(q)
        
        for page_num in range(0, len(q), songs_per_page):
            if page_num == 0:
                # Use existing embed for first page
                page_embed = embed
            else:
                # Create new embed for subsequent pages
                page_embed = discord.Embed(title=f"🎵 Song Queue (Page {page_num // songs_per_page + 1})", color=config.COLOR_QUEUED)
            
            queue_list = ""
            for i in range(page_num, min(page_num + songs_per_page, len(q))):
                song = q[i]
                duration_str = format_duration(song.get('duration')) if song.get('duration') else "?"
                queue_list += f"`{i+1}.` **{song['title']}** [{duration_str}]\n"
                queue_list += f"    Requested by {song['requester'].display_name}\n"
            
            page_embed.add_field(
                name=f"Up Next ({len(q)} total • {format_duration(total_duration)} total)",
                value=queue_list.strip(),
                inline=False
            )
            
            # Footer
            footer_parts = []
            if loop_mode == 'song':
                footer_parts.append("Loop: Song 🔂")
            elif loop_mode == 'queue':
                footer_parts.append("Loop: Queue 🔁")
            
            if len(q) > songs_per_page:
                footer_parts.append(f"Page {len(pages) + 1}/{(len(q) - 1) // songs_per_page + 1}")
            
            if footer_parts:
                page_embed.set_footer(text=" | ".join(footer_parts))
            
            pages.append(page_embed)
        
        # Send with pagination if multiple pages
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            view = QueuePaginationView(self, guild_id, pages)
            message = await ctx.send(embed=pages[0], view=view)
            view.message = message

    @commands.command(name='nowplaying', aliases=['np'], help='Shows the currently playing song (interactive message is preferred).')
    async def nowplaying(self, ctx):
        # (Same as before - provides a static alternative to the interactive message)
        guild_id = ctx.guild.id; np_info = self.current_song.get(guild_id)
        if np_info:
            embed = discord.Embed(title="▶️ Now Playing", description=f"**{np_info['title']}**", url=np_info.get('webpage_url'), color=discord.Color.green())
            embed.add_field(name="Duration", value=format_duration(np_info.get('duration')), inline=True); embed.add_field(name="Uploader", value=np_info.get('uploader', 'N/A'), inline=True)
            if np_info.get('thumbnail'): embed.set_thumbnail(url=np_info.get('thumbnail'))
            loop_mode = self.loop_mode.get(guild_id, 'off')
            footer_text = f"Requested by {np_info['requester'].display_name}"
            if loop_mode == 'song': footer_text += " | Loop: Song 🔂"
            elif loop_mode == 'queue': footer_text += " | Loop: Queue 🔁"
            embed.set_footer(text=footer_text, icon_url=np_info['requester'].display_avatar.url)
            await ctx.send(embed=embed)
        else: await ctx.send("Nothing playing.")

    @commands.command(name='clear', help='Clears the song queue.')
    @commands.has_permissions(manage_messages=True) # Or adjust perms as needed
    async def clear(self, ctx):
        guild_id = ctx.guild.id
        if guild_id in self.queues and self.queues[guild_id]: count = len(self.queues[guild_id]); self.queues[guild_id] = []; await ctx.send(f"🗑️ Cleared {count} songs.")
        else: await ctx.send("Queue empty.", delete_after=10); await ctx.message.add_reaction('❓')
    
    # --- NEW COMMANDS ---
    
    @commands.command(name='volume', aliases=['vol'], help='Set or view playback volume (0-100).')
    async def volume(self, ctx, volume: int = None):
        """Set or display current volume"""
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        if volume is None:
            # Show current volume
            current_vol = self.volume_settings.get(guild_id, config.DEFAULT_VOLUME)
            await ctx.send(f"🔊 Current volume: **{current_vol}%**")
            return
        
        # Validate range
        if not 0 <= volume <= 100:
            await ctx.send("Volume must be between 0 and 100.", delete_after=10)
            return
        
        # Set volume
        self.volume_settings[guild_id] = volume
        
        # If currently playing, restart with new volume
        if vc and (vc.is_playing() or vc.is_paused()):
            await ctx.send(f"🔊 Volume set to **{volume}%**. Will apply to next song.")
        else:
            await ctx.send(f"🔊 Volume set to **{volume}%**")
        
        await ctx.message.add_reaction('✅')
    
    @commands.command(name='replay', aliases=['restart'], help='Restart the current song from the beginning.')
    async def replay(self, ctx):
        """Restart current song"""
        vc = ctx.voice_client
        guild_id = ctx.guild.id
        
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("Nothing is playing.", delete_after=10)
            return
        
        current_song_info = self.current_song.get(guild_id)
        if not current_song_info:
            await ctx.send("No song information available.", delete_after=10)
            return
        
        # Add current song to front of queue
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        
        song_copy = current_song_info.copy()
        self.queues[guild_id].insert(0, song_copy)
        
        # Stop current playback (will trigger play_next)
        vc.stop()
        await ctx.send("🔄 Restarting song...")
        await ctx.message.add_reaction('✅')
    
    @commands.command(name='seek', help='Jump to a specific time in the current song (e.g., 1:30, 90).')
    async def seek(self, ctx, *, timestamp: str):
        """Seek to a specific time in current song (simplified version)"""
        seconds = parse_time(timestamp)
        if seconds is None:
            await ctx.send("Invalid time format. Use: `1:30`, `90`, or `1m30s`", delete_after=10)
            return
        
        guild_id = ctx.guild.id
        current_song_info = self.current_song.get(guild_id)
        
        if not current_song_info:
            await ctx.send("No song currently playing.", delete_after=10)
            return
        
        # For now, this is a simplified version - full implementation needs FFmpeg seek
        # which would require modifying the playback to start at a specific position
        await ctx.send(f"⏩ Seeking to {format_duration(seconds)}...")
        await ctx.send("Note: Full seek support requires FFmpeg position control (feature coming soon)", delete_after=10)
    
    @commands.command(name='previous', aliases=['prev', 'back'], help='Play the previously played song.')
    async def previous(self, ctx):
        """Play the previous song from history"""
        guild_id = ctx.guild.id
        history = self.playback_history.get(guild_id, [])
        
        if len(history) < 2:  # Need at least 2 songs (current + previous)
            await ctx.send("No previous song in history.", delete_after=10)
            return
        
        # Get previous song (second to last in history)
        previous_song = history[-2].copy()
        
        # Add to front of queue
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        self.queues[guild_id].insert(0, previous_song)
        
        # Skip current song
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        
        await ctx.send(f"⏮️ Playing previous: **{previous_song['title']}**")
        await ctx.message.add_reaction('✅')
    
    @commands.command(name='history', help='Show recently played songs.')
    async def history(self, ctx):
        """Display playback history"""
        guild_id = ctx.guild.id
        history = self.playback_history.get(guild_id, [])
        
        if not history:
            await ctx.send("No playback history yet.", delete_after=10)
            return
        
        embed = discord.Embed(title="📜 Playback History", color=config.COLOR_INFO)
        
        history_text = ""
        for i, song in enumerate(reversed(history[-10:]), 1):  # Last 10 songs
            history_text += f"{i}. **{song['title']}** (by {song['requester'].display_name})\n"
        
        embed.description = history_text
        embed.set_footer(text=f"Showing last {min(len(history), 10)} songs")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='lyrics', help='Show lyrics for current song or search query.')
    async def lyrics(self, ctx, *, query: str = None):
        """Fetch and display song lyrics"""
        if not config.ENABLE_LYRICS:
            await ctx.send("Lyrics feature is disabled.", delete_after=10)
            return
        
        guild_id = ctx.guild.id
        
        # If no query, use current song
        if query is None:
            current_song_info = self.current_song.get(guild_id)
            if not current_song_info:
                await ctx.send("No song playing. Provide a search query.", delete_after=10)
                return
            query = current_song_info['title']
        
        # Check cache first
        cache_key = f"lyrics:{query.lower()}"
        cached_lyrics = await self.cache.lyrics_cache.get(cache_key)
        
        if cached_lyrics:
            lyrics_text = cached_lyrics
            self.logger.info(f"Cache hit for lyrics: {query}")
        else:
            # Fetch lyrics
            async with ctx.typing():
                artist, title = self.lyrics_provider.extract_artist_title_from_youtube(query)
                lyrics_text = await self.lyrics_provider.fetch_lyrics(artist, title)
            
            if not lyrics_text:
                await ctx.send(f"❌ Lyrics not found for: **{query}**")
                return
            
            # Cache the lyrics
            await self.cache.lyrics_cache.set(cache_key, lyrics_text, config.METADATA_CACHE_TTL)
        
        # Format and send lyrics in chunks
        chunks = self.lyrics_provider.format_lyrics(lyrics_text, 2000)
        
        for i, chunk in enumerate(chunks[:3], 1):  # Limit to 3 embeds
            embed = discord.Embed(
                title=f"📝 Lyrics: {query}" if i == 1 else f"📝 Lyrics (continued {i}/{len(chunks)})",
                description=chunk,
                color=config.COLOR_INFO
            )
            await ctx.send(embed=embed)
    
    @commands.command(name='stats', aliases=['botinfo', 'info'], help='Show bot statistics.')
    async def stats(self, ctx):
        """Display bot statistics"""
        # Calculate uptime
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = format_duration(uptime_seconds)
        
        # Count songs in all queues
        total_queued = sum(len(q) for q in self.queues.values())
        
        # Get cache stats
        cache_stats = self.cache.get_all_stats()
        
        embed = discord.Embed(title="📊 Bot Statistics", color=config.COLOR_INFO)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Voice Connections", value=str(len(self.bot.voice_clients)), inline=True)
        embed.add_field(name="Total Queued Songs", value=str(total_queued), inline=True)
        
        # Cache stats
        meta_stats = cache_stats['metadata']
        embed.add_field(
            name="Cache Performance",
            value=f"Hit Rate: {meta_stats['hit_rate']}\nCached Items: {meta_stats['size']}/{meta_stats['max_size']}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='move', help='Move a song in the queue (e.g., -move 3 1).')
    async def move(self, ctx, from_pos: int, to_pos: int):
        """Move song from one position to another"""
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])
        
        if not queue:
            await ctx.send("Queue is empty.", delete_after=10)
            return
        
        if not (1 <= from_pos <= len(queue)) or not (1 <= to_pos <= len(queue)):
            await ctx.send(f"Invalid positions. Queue has {len(queue)} songs.", delete_after=10)
            return
        
        # Move the song
        song = queue.pop(from_pos - 1)
        queue.insert(to_pos - 1, song)
        
        await ctx.send(f"✅ Moved **{song['title']}** from position {from_pos} to {to_pos}")
        await ctx.message.add_reaction('✅')



# --- Cog Setup Function ---
async def setup(bot):
    # (Keep setup as before)
    ydl_logger = logging.getLogger('yt_dlp')
    if not ydl_logger.hasHandlers(): ydl_logger.setLevel(logging.WARNING)
    await bot.add_cog(MusicCog(bot))
    print("Music Cog Loaded (with threadsafe after_handler fix)")