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
import os

# Import config and utilities
import config
from utils.helpers import format_duration, parse_time, create_progress_bar, format_time_until, calculate_total_queue_duration
from utils.cache import GuildCache
from utils.lyrics import LyricsProvider
from utils.database import RedisManager

# --- FFmpeg and yt-dlp Options ---
# Use config options
PLAYLIST_URL_PATTERN = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(playlist)\?(list=.*)$')

# --- Music Control View (Updated with Shuffle Button) ---
class MusicControlView(discord.ui.View):
    def __init__(self, cog_ref, timeout=None):
        super().__init__(timeout=timeout)
        self.cog = cog_ref
        self.message = None
        self.ctx_ref = None
        self.interaction = None

    def _get_vc(self):
        if self.cog and self.cog.bot.guilds:
             target_guild = None
             if self.interaction and self.interaction.guild: target_guild = self.interaction.guild
             elif self.message and self.message.guild: target_guild = self.message.guild
             elif self.ctx_ref and self.ctx_ref.guild: target_guild = self.ctx_ref.guild 
             if target_guild: return discord.utils.get(self.cog.bot.voice_clients, guild=target_guild)
        return None

    def update_buttons(self, interaction: discord.Interaction = None):
        if interaction: self.interaction = interaction
        target_guild: discord.Guild = None
        if self.interaction and self.interaction.guild: target_guild = self.interaction.guild
        elif self.message and self.message.guild: target_guild = self.message.guild
        elif self.ctx_ref and self.ctx_ref.guild: target_guild = self.ctx_ref.guild
        if not target_guild: self.cog.logger.warning("update_buttons no guild context."); return
        guild_id = target_guild.id
        vc = discord.utils.get(self.cog.bot.voice_clients, guild=target_guild)

        # Load loop mode from Redis if not in memory
        loop_mode = self.cog.loop_mode.get(guild_id)
        if loop_mode is None:
            loop_mode = self.cog.db.get_loop_mode(guild_id)
            self.cog.loop_mode[guild_id] = loop_mode

        pause_resume_button = discord.utils.get(self.children, custom_id="pause_resume")
        loop_button = discord.utils.get(self.children, custom_id="loop")
        
        is_paused = vc and vc.is_paused(); is_playing = vc and vc.is_playing()

        if is_paused:
            pause_resume_button.emoji = '▶️'; pause_resume_button.style = discord.ButtonStyle.success
        elif is_playing:
            pause_resume_button.emoji = '⏸️'; pause_resume_button.style = discord.ButtonStyle.secondary
        else:
            pause_resume_button.emoji = '▶️'; pause_resume_button.style = discord.ButtonStyle.secondary

        if loop_mode == 'song':
            loop_button.emoji = '🔂'; loop_button.style = discord.ButtonStyle.success
        elif loop_mode == 'queue':
            loop_button.emoji = '🔁'; loop_button.style = discord.ButtonStyle.success
        else: # Off
            loop_button.emoji = '🚫'; loop_button.style = discord.ButtonStyle.secondary



    @discord.ui.button(label="", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="pause_resume")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = self._get_vc()
        if not vc: return
        if vc.is_playing(): vc.pause()
        elif vc.is_paused(): vc.resume()
        self.update_buttons(interaction)
        if self.message: await self.message.edit(view=self)

    @discord.ui.button(label="", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = self._get_vc()
        if vc: vc.stop()

    @discord.ui.button(label="", emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = self._get_vc()
        if vc: 
            guild_id = vc.guild.id
            if guild_id in self.cog.queues: self.cog.queues[guild_id] = []
            self.cog.db.clear_queue(guild_id) # Clear from Redis
            if guild_id in self.cog.current_song: del self.cog.current_song[guild_id]
            await self.cog.delete_now_playing_message(guild_id)
            vc.stop()

    @discord.ui.button(label="", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog: return
        guild_id = interaction.guild.id
        
        current = self.cog.loop_mode.get(guild_id)
        if current is None:
            current = self.cog.db.get_loop_mode(guild_id)
            
        new_mode = 'song' if current == 'off' else 'queue' if current == 'song' else 'off'
        self.cog.loop_mode[guild_id] = new_mode
        self.cog.db.set_loop_mode(guild_id, new_mode) # Persist to Redis
        self.update_buttons(interaction)
        if self.message: await self.message.edit(view=self)

    @discord.ui.button(label="", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog: return
        guild_id = interaction.guild.id
        if guild_id in self.cog.queues and len(self.cog.queues[guild_id]) > 1:
            random.shuffle(self.cog.queues[guild_id])
            self.cog.db.save_queue(guild_id, self.cog.queues[guild_id]) # Save shuffled queue
            
# --- Main Cog ---
class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('music_bot')
        self.start_time = time.time()
        self.cache = GuildCache()
        self.lyrics_provider = LyricsProvider()
        self.db = RedisManager(host=os.getenv('REDIS_HOST', 'redis'))
        
        self.queues = {}  # guild_id: list of song_info dicts
        self.loop_mode = {}  # guild_id: 'off', 'song', 'queue'
        self.volume = {}  # guild_id: float (0.0 - 1.0)
        self.current_song = {}  # guild_id: song_info dict
        self.now_playing_messages = {} # guild_id: (message, view)
        self.vote_skip_voters = {}  # guild_id: set of user_ids
        self.is_disconnecting = set() # guild_id
        self.seeking_guilds = set() # guild_id
        self.song_start_times = {} # guild_id: timestamp
        self.audio_filters = {} # guild_id: filter_name

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info(f'Music Cog ready as {self.bot.user}')
        # Restore queues from Redis
        for guild in self.bot.guilds:
            queue = self.db.load_queue(guild.id)
            if queue:
                self.queues[guild.id] = queue
                self.logger.info(f"Restored queue for guild {guild.name} ({len(queue)} songs)")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            
            # Check if this was an intentional disconnect
            if guild_id in self.is_disconnecting:
                self.is_disconnecting.remove(guild_id)
                self.logger.info(f"Intentional disconnect G:{guild_id} - skipping cleanup in listener")
                return

            self.logger.info(f"Bot disconnected VC G:{guild_id}")
            if guild_id in self.queues: self.queues[guild_id].clear()
            self.db.clear_queue(guild_id) # Clear Redis queue
            if guild_id in self.current_song: del self.current_song[guild_id]
            if guild_id in self.loop_mode: del self.loop_mode[guild_id]
            await self.delete_now_playing_message(guild_id)
            return

        if not member.bot and before.channel != after.channel:
            if before.channel:
                # Check if bot is alone
                bot_in_channel = any(m.id == self.bot.user.id for m in before.channel.members)
                if bot_in_channel:
                    non_bots = [m for m in before.channel.members if not m.bot]
                    if not non_bots:
                        vc = discord.utils.get(self.bot.voice_clients, guild=before.channel.guild)
                        if vc:
                            self.logger.info(f"Bot alone in {before.channel.name}, disconnecting...")
                            await vc.disconnect()

    async def delete_now_playing_message(self, guild_id):
        if guild_id in self.now_playing_messages:
            message_id = self.now_playing_messages[guild_id]
            del self.now_playing_messages[guild_id]

    async def _load_remaining_playlist(self, ctx, query, initial_count):
        """Background task to load the rest of a large playlist"""
        try:
            ydl_opts = config.YDL_BASE_OPTIONS.copy()
            ydl_opts['extract_flat'] = True
            ydl_opts['playliststart'] = initial_count + 1
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False)
                
                if 'entries' in info:
                    new_songs = list(info['entries'])
                    if not new_songs: return
                    
                    if ctx.guild.id not in self.queues:
                        self.queues[ctx.guild.id] = []
                        
                    self.queues[ctx.guild.id].extend(new_songs)
                    self.db.save_queue(ctx.guild.id, self.queues[ctx.guild.id])
                    
                    await ctx.send(f"✅ Loaded {len(new_songs)} more songs from playlist.")
                    
        except Exception as e:
            self.logger.error(f"Error loading remaining playlist: {e}")

    async def search_and_get_info(self, query):
        ydl_opts = config.YDL_BASE_OPTIONS.copy()
        is_playlist = bool(PLAYLIST_URL_PATTERN.match(query))
        
        if is_playlist:
            ydl_opts['extract_flat'] = True
            ydl_opts['noplaylist'] = False
        else:
            ydl_opts['extract_flat'] = False
            ydl_opts['noplaylist'] = True

        try:
            # Check for Spotify URL
            if "open.spotify.com" in query:
                # Placeholder for Spotify handling
                pass

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False)
                
                if 'entries' in info:
                    return info['entries']
                else:
                    return [info]
        except Exception as e:
            self.logger.error(f"YTDL error: {e}")
            
            # Smart Search Fallback
            if "http" in query: # If it looked like a URL
                self.logger.info(f"URL failed, trying smart search for: {query}")
                try:
                    search_query = f"ytsearch:{query}"
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                        if 'entries' in info and info['entries']:
                            return [info['entries'][0]]
                except Exception as inner_e:
                    self.logger.error(f"Smart search failed: {inner_e}")
            
            return {'error': str(e)}

    def play_next(self, ctx):
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        if not vc: return
        
        if guild_id in self.seeking_guilds:
            self.seeking_guilds.remove(guild_id)
            # Don't pop from queue if seeking, just replay current
            if guild_id in self.current_song:
                pass # Logic handled in seek
        else:
            if guild_id in self.queues and self.queues[guild_id]:
                # Loop logic
                loop_mode = self.loop_mode.get(guild_id, 'off')
                if loop_mode == 'song':
                    if guild_id in self.current_song:
                        self.queues[guild_id].insert(0, self.current_song[guild_id])
                elif loop_mode == 'queue':
                    if guild_id in self.current_song:
                        self.queues[guild_id].append(self.current_song[guild_id])
                
                # Get next song
                song_info = self.queues[guild_id].pop(0)
                self.current_song[guild_id] = song_info
                self.db.save_queue(guild_id, self.queues[guild_id]) # Update Redis
                
                # Schedule async play
                asyncio.run_coroutine_threadsafe(self._play_song(ctx, song_info), self.bot.loop)
            else:
                # Queue empty
                if guild_id in self.current_song: del self.current_song[guild_id]
                asyncio.run_coroutine_threadsafe(self.delete_now_playing_message(guild_id), self.bot.loop)

    async def _play_song(self, ctx, song_info):
        """Async helper to play a song with URL refresh if needed"""
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        if not vc:
            return
        
        try:
            url = song_info.get('url')
            # Re-extract if URL expired or missing (common with extract_flat)
            if not url:
                webpage_url = song_info.get('webpage_url') or song_info.get('original_url')
                if webpage_url:
                    self.logger.info(f"Re-extracting stream URL for: {song_info.get('title')}")
                    refreshed = await self.search_and_get_info(webpage_url)
                    if refreshed and not isinstance(refreshed, dict) and refreshed:
                        song_info = refreshed[0]
                        self.current_song[guild_id] = song_info
                        url = song_info.get('url')
            
            if not url:
                self.logger.error(f"Could not get stream URL for: {song_info.get('title')}")
                self.play_next(ctx)
                return
                
            volume = self.volume.get(guild_id)
            if volume is None:
                volume = self.db.get_volume(guild_id)
                self.volume[guild_id] = volume
            
            audio_filter = self.audio_filters.get(guild_id)
            if audio_filter is None:
                audio_filter = self.db.get_filter(guild_id)
                self.audio_filters[guild_id] = audio_filter

            ffmpeg_opts = config.get_ffmpeg_options(volume=volume, filter_name=audio_filter)
            source = discord.FFmpegOpusAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: self.after_play_handler(e, ctx))
            
            self.song_start_times[guild_id] = time.time()
            await self.send_now_playing(ctx, song_info)
            
        except Exception as e:
            self.logger.error(f"Error playing song: {e}")
            self.play_next(ctx)

    def after_play_handler(self, error, ctx):
        if error:
            self.logger.error(f"Player error: {error}")
        self.play_next(ctx)

    async def send_now_playing(self, ctx, song_info):
        guild_id = ctx.guild.id
        embed = discord.Embed(title="Now Playing", description=f"[{song_info.get('title')}]({song_info.get('webpage_url')})", color=config.COLOR_SUCCESS)
        view = MusicControlView(self)
        view.update_buttons() # Set initial button states
        message = await ctx.send(embed=embed, view=view)
        self.now_playing_messages[guild_id] = message.id # Store ID

    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.command(name='play', aliases=['p'], help='Plays a song from YouTube.')
    async def play(self, ctx, *, query: str):
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel!")
            return

        target_channel = ctx.author.voice.channel
        vc = ctx.voice_client

        if not vc:
            try:
                vc = await target_channel.connect()
            except discord.errors.Forbidden:
                await ctx.send("I do not have permission to join your voice channel.")
                return
            except Exception as e:
                await ctx.send(f"Error connecting: {e}")
                return
        elif vc.channel != target_channel:
            await vc.move_to(target_channel)

        results = await self.search_and_get_info(query)
        
        if isinstance(results, dict) and 'error' in results:
            await ctx.send(f"Error: {results['error']}")
            return
            
        if not results:
            await ctx.send("No results found.")
            return

        if ctx.guild.id not in self.queues:
            self.queues[ctx.guild.id] = []

        added = 0
        
        # Handle large playlists
        is_large_playlist = len(results) > 20
        initial_load = results[:20] if is_large_playlist else results
        
        for song in initial_load:
            self.queues[ctx.guild.id].append(song)
            added += 1
            
        # Save queue to Redis
        self.db.save_queue(ctx.guild.id, self.queues[ctx.guild.id])
            
        if added == 1:
            await ctx.send(f"Added **{initial_load[0].get('title')}** to queue.")
        else:
            msg = f"Added {added} songs to queue."
            if is_large_playlist:
                msg += f" Loading {len(results) - 20} more in background..."
                # Launch background task
                asyncio.create_task(self._load_remaining_playlist(ctx, query, 20))
            await ctx.send(msg)

        if not vc.is_playing() and not vc.is_paused():
            self.play_next(ctx)

    @commands.cooldown(1, 2, commands.BucketType.user)
    @commands.command(name='skip', aliases=['s'], help='Skips the current song.')
    async def skip(self, ctx):
        vc = ctx.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("Nothing to skip.", delete_after=10)
            await ctx.message.add_reaction('❓')
            return

        guild_id = ctx.guild.id
        current_song = self.current_song.get(guild_id)
        requester = current_song.get('requester') if current_song else None
        
        is_admin = ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.move_members
        is_requester = requester and ctx.author.id == requester.id
        
        if not is_admin and not is_requester:
            listeners = [member for member in vc.channel.members if not member.bot]
            listener_count = len(listeners)
            
            if listener_count > 0:
                required_votes = int(listener_count * config.VOTE_SKIP_THRESHOLD)
                if required_votes < 1: required_votes = 1
                
                if guild_id not in self.vote_skip_voters:
                    self.vote_skip_voters[guild_id] = set()
                
                if ctx.author.id in self.vote_skip_voters[guild_id]:
                    await ctx.send("You have already voted to skip!", delete_after=5)
                    return
                
                self.vote_skip_voters[guild_id].add(ctx.author.id)
                current_votes = len(self.vote_skip_voters[guild_id])
                
                if current_votes < required_votes:
                    await ctx.send(f"🗳️ Vote to skip: {current_votes}/{required_votes}")
                    return
                else:
                    await ctx.send("🗳️ Vote threshold met! Skipping...")
        
        await ctx.message.add_reaction('⏭️')
        if guild_id in self.vote_skip_voters:
            self.vote_skip_voters[guild_id].clear()
        vc.stop()

    @commands.command(name='stop', help='Stops playback and clears queue.')
    async def stop(self, ctx):
        vc = ctx.voice_client
        if vc:
            self.queues[ctx.guild.id] = []
            self.db.clear_queue(ctx.guild.id) # Clear Redis
            vc.stop()
            await ctx.send("Stopped and cleared queue. ⏹️")

    @commands.command(name='volume', aliases=['vol'], help='Sets the volume (0-100).')
    async def set_volume(self, ctx, volume: int):
        if not 0 <= volume <= 100:
            await ctx.send("Volume must be between 0 and 100.")
            return
            
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        
        vol_float = volume / 100
        self.volume[guild_id] = vol_float
        self.db.set_volume(guild_id, vol_float) # Persist
        
        if vc and vc.source:
            vc.source.volume = vol_float
            
        await ctx.send(f"Volume set to {volume}% 🔊")

    @commands.command(name='loop', help='Cycles loop mode.')
    async def loop(self, ctx):
        guild_id = ctx.guild.id
        current = self.loop_mode.get(guild_id)
        if current is None:
             current = self.db.get_loop_mode(guild_id)
             
        new_mode = 'song' if current == 'off' else 'queue' if current == 'song' else 'off'
        self.loop_mode[guild_id] = new_mode
        self.db.set_loop_mode(guild_id, new_mode) # Persist
        
        await ctx.send(f"Loop mode: **{new_mode}**")

    @commands.command(name='seek', help='Seek to a specific timestamp (e.g., 1:30, 90s).')
    async def seek(self, ctx, timestamp: str):
        vc = ctx.voice_client
        guild_id = ctx.guild.id
        
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("Nothing is playing.", delete_after=10)
            return

        seconds = parse_time(timestamp)
        if seconds is None:
            await ctx.send("❌ Invalid timestamp format. Use MM:SS or seconds (e.g., 1:30, 90).")
            return
            
        current_song = self.current_song.get(guild_id)
        if not current_song:
            await ctx.send("Error: No song info found.")
            return
            
        duration = current_song.get('duration')
        if duration and seconds > duration:
            await ctx.send("❌ Timestamp exceeds song duration.")
            return

        await ctx.send(f"⏩ Seeking to **{format_duration(seconds)}**...")
        
        stream_url = current_song.get('url')
        if not stream_url:
            await ctx.send("❌ Cannot seek: Stream URL lost.")
            return

        try:
            volume = self.volume.get(guild_id)
            if volume is None:
                volume = self.db.get_volume(guild_id)
                self.volume[guild_id] = volume
            
            # Get filter
            audio_filter = self.audio_filters.get(guild_id)
            if audio_filter is None:
                audio_filter = self.db.get_filter(guild_id)
                self.audio_filters[guild_id] = audio_filter

            ffmpeg_opts = config.get_ffmpeg_options(volume=volume, filter_name=audio_filter)
            base_before_options = ffmpeg_opts.get('before_options', '')
            ffmpeg_opts['before_options'] = f"-ss {seconds} {base_before_options}"
            
            new_source = discord.FFmpegOpusAudio(stream_url, **ffmpeg_opts)
            
            self.song_start_times[guild_id] = time.time() - seconds
            self.seeking_guilds.add(guild_id)
            
            vc.stop()
            vc.play(new_source, after=lambda e: self.after_play_handler(e, ctx))
            
        except Exception as e:
            self.logger.error(f"Seek error: {e}")
            await ctx.send(f"❌ Error seeking: {e}")
            if guild_id in self.seeking_guilds:
                self.seeking_guilds.discard(guild_id)

    @commands.command(name='filter', aliases=['effect'], help='Apply audio filter (nightcore, vaporwave, bassboost, 8d, off).')
    async def filter(self, ctx, filter_name: str):
        guild_id = ctx.guild.id
        valid_filters = ['off', 'nightcore', 'vaporwave', 'bassboost', '8d', 'karaoke']
        
        if filter_name.lower() not in valid_filters:
            await ctx.send(f"❌ Invalid filter. Available: {', '.join(valid_filters)}")
            return
            
        self.audio_filters[guild_id] = filter_name.lower()
        self.db.set_filter(guild_id, filter_name.lower())
        
        await ctx.send(f"🎵 Filter set to **{filter_name}**. Replaying to apply...")
        
        # Restart current song to apply filter
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            current_pos = time.time() - self.song_start_times.get(guild_id, time.time())
            timestamp = format_duration(int(current_pos))
            await self.seek(ctx, timestamp)

    @commands.command(name='remove', aliases=['rm'], help='Removes a song from the queue by its index.')
    async def remove(self, ctx, index: int):
        guild_id = ctx.guild.id
        if guild_id not in self.queues or not self.queues[guild_id]:
            await ctx.send("The queue is empty.", delete_after=10); await ctx.message.add_reaction('❓'); return
        queue_len = len(self.queues[guild_id])
        if not 1 <= index <= queue_len:
            await ctx.send(f"Invalid index. Must be between 1 and {queue_len}.", delete_after=10); await ctx.message.add_reaction('❌'); return
        removed_song = self.queues[guild_id].pop(index - 1)
        self.db.save_queue(guild_id, self.queues[guild_id]) # Update Redis
        await ctx.send(f"🗑️ Removed **{removed_song.get('title','Unknown Title')}** (position {index}).")
        await ctx.message.add_reaction('✅')

    @commands.command(name='shuffle', help='Shuffles the current song queue.')
    async def shuffle(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.queues or len(self.queues[guild_id]) < 2:
            await ctx.send("Not enough songs in the queue to shuffle.", delete_after=10); await ctx.message.add_reaction('❓'); return
        random.shuffle(self.queues[guild_id])
        self.db.save_queue(guild_id, self.queues[guild_id]) # Update Redis
        await ctx.send("🔀 Queue shuffled!")
        await ctx.message.add_reaction('✅')

    @commands.command(name='pause', help='Pauses the currently playing song.')
    async def pause(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.message.add_reaction('⏸️')
        elif vc and vc.is_paused():
             await ctx.send("Already paused.")
        else:
            await ctx.send("Nothing playing.")

    @commands.command(name='resume', help='Resumes the currently paused song.')
    async def resume(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.message.add_reaction('▶️')
        elif vc and vc.is_playing():
            await ctx.send("Already playing.")
        else:
            await ctx.send("Nothing paused.")

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(name='lyrics', help='Get lyrics for the current song or a query.')
    async def lyrics(self, ctx, *, query: str = None):
        if not query:
            # Try to get current song
            guild_id = ctx.guild.id
            if guild_id in self.current_song:
                query = self.current_song[guild_id].get('title')
        
        if not query:
            await ctx.send("Please provide a song name or play something first.")
            return
            
        async with ctx.typing():
            lyrics = await self.lyrics_provider.search_lyrics(query)
            
        if not lyrics:
            await ctx.send(f"No lyrics found for '{query}'.")
            return
            
        # Split lyrics if too long
        chunks = [lyrics[i:i+4096] for i in range(0, len(lyrics), 4096)]
        
        for i, chunk in enumerate(chunks[:3], 1):
            embed = discord.Embed(
                title=f"📝 Lyrics: {query}" if i == 1 else f"📝 Lyrics (continued {i}/{len(chunks)})",
                description=chunk,
                color=config.COLOR_INFO
            )
            await ctx.send(embed=embed)

    @commands.command(name='stats', aliases=['botinfo', 'info'], help='Show bot statistics.')
    async def stats(self, ctx):
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = format_duration(uptime_seconds)
        total_queued = sum(len(q) for q in self.queues.values())
        cache_stats = self.cache.get_all_stats()
        
        embed = discord.Embed(title="📊 Bot Statistics", color=config.COLOR_INFO)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Voice Connections", value=str(len(self.bot.voice_clients)), inline=True)
        embed.add_field(name="Total Queued Songs", value=str(total_queued), inline=True)
        
        meta_stats = cache_stats['metadata']
        embed.add_field(
            name="Cache Performance",
            value=f"Hit Rate: {meta_stats['hit_rate']}\nCached Items: {meta_stats['size']}/{meta_stats['max_size']}",
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(name='move', help='Move a song in the queue (e.g., -move 3 1).')
    async def move(self, ctx, from_pos: int, to_pos: int):
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])
        
        if not queue:
            await ctx.send("Queue is empty.", delete_after=10); return
        
        if not (1 <= from_pos <= len(queue)) or not (1 <= to_pos <= len(queue)):
            await ctx.send(f"Invalid positions. Queue has {len(queue)} songs.", delete_after=10); return
        
        song = queue.pop(from_pos - 1)
        queue.insert(to_pos - 1, song)
        self.db.save_queue(guild_id, queue) # Update Redis
        
        await ctx.send(f"✅ Moved **{song['title']}** from position {from_pos} to {to_pos}")
        await ctx.message.add_reaction('✅')

    @commands.command(name='queue', aliases=['q'], help='Display the current song queue.')
    async def queue(self, ctx, page: int = 1):
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])
        current = self.current_song.get(guild_id)
        
        if not queue and not current:
            await ctx.send("The queue is empty.", delete_after=10)
            return
        
        # Pagination
        items_per_page = 10
        total_pages = max(1, (len(queue) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        embed = discord.Embed(title="🎵 Music Queue", color=config.COLOR_INFO)
        
        # Now playing
        if current:
            duration = format_duration(current.get('duration'))
            embed.add_field(
                name="Now Playing",
                value=f"[{current.get('title', 'Unknown')}]({current.get('webpage_url', '')})\n`{duration}`",
                inline=False
            )
        
        # Queue items
        if queue:
            queue_text = ""
            for i, song in enumerate(queue[start_idx:end_idx], start=start_idx + 1):
                title = song.get('title', 'Unknown')[:40]
                duration = format_duration(song.get('duration'))
                queue_text += f"`{i}.` {title} `{duration}`\n"
            
            embed.add_field(name=f"Up Next ({len(queue)} songs)", value=queue_text or "Empty", inline=False)
            
            # Total duration
            total_duration = calculate_total_queue_duration(queue)
            embed.set_footer(text=f"Page {page}/{total_pages} • Total: {format_duration(total_duration)}")
        
        await ctx.send(embed=embed)

    @commands.command(name='nowplaying', aliases=['np'], help='Show the currently playing song.')
    async def nowplaying(self, ctx):
        guild_id = ctx.guild.id
        current = self.current_song.get(guild_id)
        vc = ctx.voice_client
        
        if not current or not vc:
            await ctx.send("Nothing is currently playing.", delete_after=10)
            return
        
        # Calculate progress
        start_time = self.song_start_times.get(guild_id, time.time())
        elapsed = int(time.time() - start_time)
        duration = current.get('duration', 0)
        
        progress_bar = create_progress_bar(elapsed, duration, length=15)
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{current.get('title', 'Unknown')}]({current.get('webpage_url', '')})",
            color=config.COLOR_PLAYING
        )
        
        embed.add_field(
            name="Progress",
            value=f"{progress_bar}\n`{format_duration(elapsed)} / {format_duration(duration)}`",
            inline=False
        )
        
        # Loop mode
        loop_mode = self.loop_mode.get(guild_id, 'off')
        loop_emoji = {'off': '🚫', 'song': '🔂', 'queue': '🔁'}.get(loop_mode, '🚫')
        embed.add_field(name="Loop", value=f"{loop_emoji} {loop_mode.capitalize()}", inline=True)
        
        # Volume
        volume = self.volume.get(guild_id, 1.0)
        embed.add_field(name="Volume", value=f"🔊 {int(volume * 100)}%", inline=True)
        
        # Queue length
        queue_len = len(self.queues.get(guild_id, []))
        embed.add_field(name="Queue", value=f"📋 {queue_len} songs", inline=True)
        
        if current.get('thumbnail'):
            embed.set_thumbnail(url=current.get('thumbnail'))
        
        await ctx.send(embed=embed)

    @commands.command(name='disconnect', aliases=['leave', 'dc'], help='Disconnect the bot from voice channel.')
    async def disconnect(self, ctx):
        vc = ctx.voice_client
        guild_id = ctx.guild.id
        
        if not vc:
            await ctx.send("I'm not in a voice channel.", delete_after=10)
            return
        
        # Mark as intentional disconnect
        self.is_disconnecting.add(guild_id)
        
        # Clear queue
        if guild_id in self.queues:
            self.queues[guild_id] = []
        self.db.clear_queue(guild_id)
        
        if guild_id in self.current_song:
            del self.current_song[guild_id]
        
        await self.delete_now_playing_message(guild_id)
        await vc.disconnect()
        await ctx.send("👋 Disconnected from voice channel.")

async def setup(bot):
    ydl_logger = logging.getLogger('yt_dlp')
    if not ydl_logger.hasHandlers(): ydl_logger.setLevel(logging.WARNING)
    await bot.add_cog(MusicCog(bot))
    print("Music Cog Loaded")