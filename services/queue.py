# -*- coding: utf-8 -*-
"""
Queue management service
"""

import logging
import random
from typing import Dict, List, Optional

from models.song import Song
from models.guild_state import GuildState
from utils.database import RedisManager


logger = logging.getLogger('music_bot.queue')


class QueueService:
    """Service for managing song queues per guild"""
    
    def __init__(self, db: RedisManager):
        self.logger = logger
        self.db = db
        self._states: Dict[int, GuildState] = {}
    
    def get_state(self, guild_id: int) -> GuildState:
        """Get or create guild state"""
        if guild_id not in self._states:
            self._states[guild_id] = GuildState(guild_id=guild_id)
            # Load from Redis if available
            self._load_from_redis(guild_id)
        return self._states[guild_id]
    
    def _load_from_redis(self, guild_id: int):
        """Load queue and settings from Redis"""
        state = self._states[guild_id]
        
        # Load queue
        queue_data = self.db.load_queue(guild_id)
        if queue_data:
            state.queue = [Song.from_dict(s) for s in queue_data]
            self.logger.info(f"Loaded {len(state.queue)} songs from Redis for guild {guild_id}")
        
        # Load settings
        state.volume = self.db.get_volume(guild_id)
        state.loop_mode = self.db.get_loop_mode(guild_id)
        state.audio_filter = self.db.get_filter(guild_id)
    
    def _save_queue_to_redis(self, guild_id: int):
        """Save queue to Redis"""
        state = self._states.get(guild_id)
        if state:
            queue_data = [s.to_dict() for s in state.queue]
            self.db.save_queue(guild_id, queue_data)
    
    def add(self, guild_id: int, song: Song) -> int:
        """Add song to queue, return position"""
        state = self.get_state(guild_id)
        position = state.add_to_queue(song)
        self._save_queue_to_redis(guild_id)
        return position
    
    def add_many(self, guild_id: int, songs: List[Song]) -> int:
        """Add multiple songs to queue, return count added"""
        state = self.get_state(guild_id)
        for song in songs:
            state.add_to_queue(song)
        self._save_queue_to_redis(guild_id)
        return len(songs)
    
    def remove(self, guild_id: int, index: int) -> Optional[Song]:
        """Remove song at index (0-based)"""
        state = self.get_state(guild_id)
        song = state.remove_from_queue(index)
        if song:
            self._save_queue_to_redis(guild_id)
        return song
    
    def clear(self, guild_id: int):
        """Clear the queue"""
        state = self.get_state(guild_id)
        state.clear_queue()
        self.db.clear_queue(guild_id)
    
    def shuffle(self, guild_id: int):
        """Shuffle the queue"""
        state = self.get_state(guild_id)
        state.shuffle_queue()
        self._save_queue_to_redis(guild_id)
    
    def move(self, guild_id: int, from_pos: int, to_pos: int) -> bool:
        """Move song from one position to another (0-based)"""
        state = self.get_state(guild_id)
        success = state.move_song(from_pos, to_pos)
        if success:
            self._save_queue_to_redis(guild_id)
        return success
    
    def get_next(self, guild_id: int) -> Optional[Song]:
        """Get next song based on loop mode"""
        state = self.get_state(guild_id)
        song = state.get_next_song()
        if song:
            state.current_song = song
            self._save_queue_to_redis(guild_id)
        return song
    
    def get_current(self, guild_id: int) -> Optional[Song]:
        """Get currently playing song"""
        state = self.get_state(guild_id)
        return state.current_song
    
    def set_current(self, guild_id: int, song: Optional[Song]):
        """Set current song"""
        state = self.get_state(guild_id)
        state.current_song = song
    
    def get_queue(self, guild_id: int) -> List[Song]:
        """Get queue for guild"""
        return self.get_state(guild_id).queue
    
    # --- Settings ---
    
    def set_volume(self, guild_id: int, volume: float):
        """Set volume (0.0 - 1.0)"""
        state = self.get_state(guild_id)
        state.volume = max(0.0, min(1.0, volume))
        self.db.set_volume(guild_id, state.volume)
    
    def get_volume(self, guild_id: int) -> float:
        """Get volume"""
        return self.get_state(guild_id).volume
    
    def set_loop_mode(self, guild_id: int, mode: str):
        """Set loop mode ('off', 'song', 'queue')"""
        state = self.get_state(guild_id)
        state.loop_mode = mode
        self.db.set_loop_mode(guild_id, mode)
    
    def cycle_loop_mode(self, guild_id: int) -> str:
        """Cycle to next loop mode, return new mode"""
        state = self.get_state(guild_id)
        modes = ['off', 'song', 'queue']
        current_idx = modes.index(state.loop_mode) if state.loop_mode in modes else 0
        new_mode = modes[(current_idx + 1) % len(modes)]
        self.set_loop_mode(guild_id, new_mode)
        return new_mode
    
    def get_loop_mode(self, guild_id: int) -> str:
        """Get loop mode"""
        return self.get_state(guild_id).loop_mode
    
    def set_filter(self, guild_id: int, filter_name: str):
        """Set audio filter"""
        state = self.get_state(guild_id)
        state.audio_filter = filter_name
        self.db.set_filter(guild_id, filter_name)
    
    def get_filter(self, guild_id: int) -> str:
        """Get audio filter"""
        return self.get_state(guild_id).audio_filter
    
    # --- Vote Skip ---
    
    def add_skip_vote(self, guild_id: int, user_id: int) -> bool:
        """Add skip vote, return True if new vote"""
        state = self.get_state(guild_id)
        if user_id in state.vote_skip_users:
            return False
        state.vote_skip_users.add(user_id)
        return True
    
    def get_skip_votes(self, guild_id: int) -> int:
        """Get number of skip votes"""
        return len(self.get_state(guild_id).vote_skip_users)
    
    def reset_skip_votes(self, guild_id: int):
        """Reset skip votes"""
        self.get_state(guild_id).reset_vote_skip()
    
    # --- Song Start Time ---
    
    def set_song_start_time(self, guild_id: int, timestamp: float):
        """Set when current song started"""
        self.get_state(guild_id).song_start_time = timestamp
    
    def get_song_start_time(self, guild_id: int) -> Optional[float]:
        """Get when current song started"""
        return self.get_state(guild_id).song_start_time
    
    # --- Now Playing Message ---
    
    def set_now_playing_message(self, guild_id: int, message_id: int):
        """Set now playing message ID"""
        self.get_state(guild_id).now_playing_message_id = message_id
    
    def get_now_playing_message(self, guild_id: int) -> Optional[int]:
        """Get now playing message ID"""
        return self.get_state(guild_id).now_playing_message_id
    
    def clear_now_playing_message(self, guild_id: int):
        """Clear now playing message ID"""
        self.get_state(guild_id).now_playing_message_id = None
    
    # --- Cleanup ---
    
    def cleanup_guild(self, guild_id: int):
        """Clean up guild state (on disconnect)"""
        if guild_id in self._states:
            del self._states[guild_id]
        self.db.clear_queue(guild_id)
    
    # --- 24/7 Mode ---
    
    def set_247_mode(self, guild_id: int, enabled: bool):
        """Set 24/7 mode"""
        state = self.get_state(guild_id)
        state.is_247_mode = enabled
        self.db.set_247_mode(guild_id, enabled)
    
    def get_247_mode(self, guild_id: int) -> bool:
        """Get 24/7 mode"""
        state = self.get_state(guild_id)
        if not hasattr(state, '_247_loaded'):
            state.is_247_mode = self.db.get_247_mode(guild_id)
            state._247_loaded = True
        return state.is_247_mode
    
    # --- Auto-play ---
    
    def set_autoplay(self, guild_id: int, enabled: bool):
        """Set auto-play mode"""
        state = self.get_state(guild_id)
        state.autoplay_enabled = enabled
        self.db.set_autoplay(guild_id, enabled)
    
    def get_autoplay(self, guild_id: int) -> bool:
        """Get auto-play mode"""
        state = self.get_state(guild_id)
        if not hasattr(state, '_autoplay_loaded'):
            state.autoplay_enabled = self.db.get_autoplay(guild_id)
            state._autoplay_loaded = True
        return state.autoplay_enabled
    
    # --- Request Channel ---
    
    def set_request_channel(self, guild_id: int, channel_id: Optional[int]):
        """Set song request channel"""
        self.db.set_request_channel(guild_id, channel_id)
    
    def get_request_channel(self, guild_id: int) -> Optional[int]:
        """Get song request channel"""
        return self.db.get_request_channel(guild_id)
    
    # --- Saved Playlists ---
    
    def save_playlist(self, guild_id: int, name: str) -> int:
        """Save current queue as a playlist, return song count"""
        state = self.get_state(guild_id)
        songs = [s.to_dict() for s in state.queue]
        if state.current_song:
            songs.insert(0, state.current_song.to_dict())
        self.db.save_playlist(guild_id, name, songs)
        return len(songs)
    
    def load_playlist(self, guild_id: int, name: str) -> Optional[List[Song]]:
        """Load a saved playlist, return songs or None"""
        playlist_data = self.db.load_playlist(guild_id, name)
        if playlist_data:
            return [Song.from_dict(s) for s in playlist_data]
        return None
    
    def delete_playlist(self, guild_id: int, name: str) -> bool:
        """Delete a saved playlist"""
        return self.db.delete_playlist(guild_id, name)
    
    def list_playlists(self, guild_id: int) -> List[str]:
        """List all saved playlist names"""
        return self.db.list_playlists(guild_id)
