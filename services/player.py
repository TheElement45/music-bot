# -*- coding: utf-8 -*-
"""
Audio player service
"""

import asyncio
import logging
import time
from typing import Callable, Optional

import discord

import config
from models.song import Song
from services.queue import QueueService
from services.extractor import ExtractorService


logger = logging.getLogger('music_bot.player')


class PlayerService:
    """Service for audio playback control"""
    
    def __init__(
        self, 
        bot: discord.ext.commands.Bot,
        queue_service: QueueService,
        extractor_service: ExtractorService
    ):
        self.bot = bot
        self.logger = logger
        self.queue = queue_service
        self.extractor = extractor_service
        
        # Track seeking state per guild
        self._seeking_guilds: set = set()
        # Track intentional disconnects
        self._disconnecting_guilds: set = set()
    
    def get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        """Get voice client for guild"""
        guild = self.bot.get_guild(guild_id)
        if guild:
            return discord.utils.get(self.bot.voice_clients, guild=guild)
        return None
    
    async def connect(self, channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Connect to voice channel"""
        try:
            return await channel.connect()
        except discord.errors.Forbidden:
            self.logger.error(f"No permission to join {channel.name}")
            return None
        except Exception as e:
            self.logger.error(f"Error connecting to voice: {e}")
            return None
    
    async def disconnect(self, guild_id: int):
        """Disconnect from voice channel"""
        self._disconnecting_guilds.add(guild_id)
        
        vc = self.get_voice_client(guild_id)
        if vc:
            await vc.disconnect()
        
        self.queue.cleanup_guild(guild_id)
    
    def is_intentional_disconnect(self, guild_id: int) -> bool:
        """Check if disconnect was intentional"""
        if guild_id in self._disconnecting_guilds:
            self._disconnecting_guilds.discard(guild_id)
            return True
        return False
    
    async def play_song(
        self, 
        guild_id: int, 
        song: Song,
        after_callback: Optional[Callable] = None
    ) -> bool:
        """
        Play a song
        
        Args:
            guild_id: Guild ID
            song: Song to play
            after_callback: Callback for when song ends
            
        Returns:
            True if playback started successfully
        """
        vc = self.get_voice_client(guild_id)
        if not vc:
            self.logger.error(f"No voice client for guild {guild_id}")
            return False
        
        # Refresh URL if needed
        if not song.is_url_valid:
            refreshed = await self.extractor.refresh_url(song)
            if not refreshed:
                self.logger.error(f"Could not get stream URL for: {song.title}")
                return False
            song = refreshed
            self.queue.set_current(guild_id, song)
        
        try:
            volume = self.queue.get_volume(guild_id)
            audio_filter = self.queue.get_filter(guild_id)
            
            ffmpeg_opts = config.get_ffmpeg_options(volume=volume, filter_name=audio_filter)
            source = discord.FFmpegOpusAudio(song.url, **ffmpeg_opts)
            
            vc.play(source, after=after_callback)
            
            self.queue.set_song_start_time(guild_id, time.time())
            self.queue.reset_skip_votes(guild_id)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error playing song: {e}")
            return False
    
    async def play_next(self, guild_id: int, after_callback: Optional[Callable] = None) -> bool:
        """
        Play next song in queue
        
        Args:
            guild_id: Guild ID
            after_callback: Callback for when song ends
            
        Returns:
            True if a song was played, False if queue empty
        """
        # Skip if we're seeking (will be replayed)
        if guild_id in self._seeking_guilds:
            self._seeking_guilds.discard(guild_id)
            return False
        
        song = self.queue.get_next(guild_id)
        if not song:
            self.queue.set_current(guild_id, None)
            return False
        
        return await self.play_song(guild_id, song, after_callback)
    
    async def skip(self, guild_id: int):
        """Skip current song"""
        vc = self.get_voice_client(guild_id)
        if vc:
            self.queue.reset_skip_votes(guild_id)
            vc.stop()  # Will trigger after callback
    
    def pause(self, guild_id: int) -> bool:
        """Pause playback, return True if paused"""
        vc = self.get_voice_client(guild_id)
        if vc and vc.is_playing():
            vc.pause()
            return True
        return False
    
    def resume(self, guild_id: int) -> bool:
        """Resume playback, return True if resumed"""
        vc = self.get_voice_client(guild_id)
        if vc and vc.is_paused():
            vc.resume()
            return True
        return False
    
    def is_playing(self, guild_id: int) -> bool:
        """Check if playing"""
        vc = self.get_voice_client(guild_id)
        return vc is not None and vc.is_playing()
    
    def is_paused(self, guild_id: int) -> bool:
        """Check if paused"""
        vc = self.get_voice_client(guild_id)
        return vc is not None and vc.is_paused()
    
    async def seek(self, guild_id: int, seconds: int, after_callback: Optional[Callable] = None) -> bool:
        """
        Seek to position in current song
        
        Args:
            guild_id: Guild ID
            seconds: Position in seconds
            after_callback: Callback for when song ends
            
        Returns:
            True if seek successful
        """
        vc = self.get_voice_client(guild_id)
        current_song = self.queue.get_current(guild_id)
        
        if not vc or not current_song:
            return False
        
        if not current_song.url:
            refreshed = await self.extractor.refresh_url(current_song)
            if not refreshed:
                return False
            current_song = refreshed
            self.queue.set_current(guild_id, current_song)
        
        try:
            volume = self.queue.get_volume(guild_id)
            audio_filter = self.queue.get_filter(guild_id)
            
            ffmpeg_opts = config.get_ffmpeg_options(volume=volume, filter_name=audio_filter)
            base_before_options = ffmpeg_opts.get('before_options', '')
            ffmpeg_opts['before_options'] = f"-ss {seconds} {base_before_options}"
            
            source = discord.FFmpegOpusAudio(current_song.url, **ffmpeg_opts)
            
            # Mark as seeking so play_next doesn't pop queue
            self._seeking_guilds.add(guild_id)
            
            # Update start time to account for seek position
            self.queue.set_song_start_time(guild_id, time.time() - seconds)
            
            vc.stop()
            vc.play(source, after=after_callback)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Seek error: {e}")
            self._seeking_guilds.discard(guild_id)
            return False
    
    async def apply_filter(
        self, 
        guild_id: int, 
        filter_name: str,
        after_callback: Optional[Callable] = None
    ) -> bool:
        """
        Apply audio filter by restarting playback
        
        Args:
            guild_id: Guild ID
            filter_name: Filter to apply
            after_callback: Callback for when song ends
            
        Returns:
            True if filter applied
        """
        self.queue.set_filter(guild_id, filter_name)
        
        # Calculate current position
        start_time = self.queue.get_song_start_time(guild_id)
        if start_time:
            current_pos = int(time.time() - start_time)
            return await self.seek(guild_id, current_pos, after_callback)
        
        return False
    
    def get_current_position(self, guild_id: int) -> int:
        """Get current playback position in seconds"""
        start_time = self.queue.get_song_start_time(guild_id)
        if start_time:
            return int(time.time() - start_time)
        return 0
