# -*- coding: utf-8 -*-
"""
Guild state data model
"""

from dataclasses import dataclass, field
from typing import Optional, Literal, List
from .song import Song


LoopMode = Literal['off', 'song', 'queue']
FilterName = Literal['off', 'nightcore', 'vaporwave', 'bassboost', '8d', 'karaoke']


@dataclass
class GuildState:
    """Per-guild music state"""
    
    guild_id: int
    queue: List[Song] = field(default_factory=list)
    current_song: Optional[Song] = None
    loop_mode: LoopMode = 'off'
    volume: float = 1.0  # 0.0 - 1.0
    audio_filter: FilterName = 'off'
    is_paused: bool = False
    song_start_time: Optional[float] = None  # timestamp when song started
    
    # Feature flags
    is_247_mode: bool = False  # Stay connected even when alone
    autoplay_enabled: bool = False  # Auto-play recommendations when queue empty
    
    # UI state
    now_playing_message_id: Optional[int] = None
    
    # Vote skip tracking
    vote_skip_users: set = field(default_factory=set)
    
    def add_to_queue(self, song: Song) -> int:
        """Add song to queue, return position"""
        self.queue.append(song)
        return len(self.queue)
    
    def remove_from_queue(self, index: int) -> Optional[Song]:
        """Remove song at index (0-based), return removed song"""
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None
    
    def get_next_song(self) -> Optional[Song]:
        """Get next song based on loop mode"""
        if not self.queue and self.loop_mode != 'song':
            return None
        
        if self.loop_mode == 'song' and self.current_song:
            # Repeat current song
            return self.current_song
        
        if self.loop_mode == 'queue' and self.current_song:
            # Add current to end of queue
            self.queue.append(self.current_song)
        
        if self.queue:
            return self.queue.pop(0)
        
        return None
    
    def clear_queue(self):
        """Clear the queue"""
        self.queue.clear()
        self.current_song = None
    
    def shuffle_queue(self):
        """Shuffle the queue"""
        import random
        random.shuffle(self.queue)
    
    def move_song(self, from_pos: int, to_pos: int) -> bool:
        """Move song from one position to another (0-based)"""
        if not (0 <= from_pos < len(self.queue) and 0 <= to_pos < len(self.queue)):
            return False
        song = self.queue.pop(from_pos)
        self.queue.insert(to_pos, song)
        return True
    
    def reset_vote_skip(self):
        """Reset vote skip tracking"""
        self.vote_skip_users.clear()
    
    @property
    def queue_duration(self) -> int:
        """Total duration of queue in seconds"""
        return sum(song.duration for song in self.queue)
    
    @property
    def queue_length(self) -> int:
        """Number of songs in queue"""
        return len(self.queue)
