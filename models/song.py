# -*- coding: utf-8 -*-
"""
Song data model
"""

from dataclasses import dataclass, field
from typing import Optional, Any
import discord


@dataclass
class Song:
    """Represents a song in the queue"""
    
    title: str
    url: str  # Stream URL
    webpage_url: str  # Original URL (YouTube, etc.)
    duration: int  # Duration in seconds
    thumbnail: Optional[str] = None
    requester: Optional[discord.Member] = None
    original_url: Optional[str] = None  # Backup URL for re-extraction
    
    # Additional metadata
    uploader: Optional[str] = None
    view_count: Optional[int] = None
    
    @classmethod
    def from_ytdl_info(cls, info: dict, requester: Optional[discord.Member] = None) -> 'Song':
        """Create a Song from yt-dlp extracted info"""
        return cls(
            title=info.get('title', 'Unknown Title'),
            url=info.get('url', ''),
            webpage_url=info.get('webpage_url', info.get('original_url', '')),
            duration=info.get('duration', 0) or 0,
            thumbnail=info.get('thumbnail'),
            requester=requester,
            original_url=info.get('original_url'),
            uploader=info.get('uploader'),
            view_count=info.get('view_count'),
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage"""
        return {
            'title': self.title,
            'url': self.url,
            'webpage_url': self.webpage_url,
            'duration': self.duration,
            'thumbnail': self.thumbnail,
            'original_url': self.original_url,
            'uploader': self.uploader,
            'view_count': self.view_count,
            # Note: requester is not serialized (can't store discord.Member)
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Song':
        """Create a Song from dictionary (Redis)"""
        return cls(
            title=data.get('title', 'Unknown Title'),
            url=data.get('url', ''),
            webpage_url=data.get('webpage_url', ''),
            duration=data.get('duration', 0),
            thumbnail=data.get('thumbnail'),
            original_url=data.get('original_url'),
            uploader=data.get('uploader'),
            view_count=data.get('view_count'),
        )
    
    @property
    def is_url_valid(self) -> bool:
        """Check if stream URL is present"""
        return bool(self.url)
    
    def __str__(self) -> str:
        return f"{self.title} ({self.formatted_duration})"
    
    @property
    def formatted_duration(self) -> str:
        """Return duration as MM:SS or HH:MM:SS"""
        if self.duration <= 0:
            return "N/A"
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
