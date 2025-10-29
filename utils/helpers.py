# -*- coding: utf-8 -*-
"""
Helper functions for the Discord Music Bot
"""

import re
from typing import Optional, Union
import datetime


def format_duration(seconds: Optional[int]) -> str:
    """
    Format duration in seconds to human-readable format (HH:MM:SS or MM:SS)
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string
    """
    if seconds is None:
        return "N/A"
    
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "N/A"
    
    if seconds < 0:
        return "N/A"
    
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def parse_time(time_str: str) -> Optional[int]:
    """
    Parse time string to seconds
    Supports formats: "1:30", "90", "1m30s", "1h30m", "1h30m15s"
    
    Args:
        time_str: Time string to parse
    
    Returns:
        Total seconds or None if invalid
    """
    if not time_str:
        return None
    
    time_str = time_str.strip().lower()
    
    # Try parsing as plain number (seconds)
    try:
        return int(time_str)
    except ValueError:
        pass
    
    # Try parsing HH:MM:SS or MM:SS format
    if ':' in time_str:
        parts = time_str.split(':')
        try:
            if len(parts) == 2:  # MM:SS
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            elif len(parts) == 3:  # HH:MM:SS
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
        except ValueError:
            pass
    
    # Try parsing with units (1h30m15s, 1m30s, etc.)
    pattern = r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
    match = re.fullmatch(pattern, time_str)
    
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        if hours == 0 and minutes == 0 and seconds == 0:
            return None
        
        return hours * 3600 + minutes * 60 + seconds
    
    return None


def create_progress_bar(current: int, total: int, length: int = 10, filled: str = '█', empty: str = '░') -> str:
    """
    Create a text-based progress bar
    
    Args:
        current: Current position in seconds
        total: Total duration in seconds
        length: Length of the progress bar in characters
        filled: Character for filled portion
        empty: Character for empty portion
    
    Returns:
        Progress bar string
    """
    if total <= 0 or current < 0:
        return f"[{empty * length}]"
    
    if current > total:
        current = total
    
    filled_length = int((current / total) * length)
    bar = filled * filled_length + empty * (length - filled_length)
    
    return f"[{bar}]"


def format_time_until(position_in_queue: int, current_song_remaining: int, queue_songs: list) -> str:
    """
    Calculate and format estimated time until a song plays
    
    Args:
        position_in_queue: Position in queue (0-indexed)
        current_song_remaining: Remaining time of current song in seconds
        queue_songs: List of songs in queue before this song
    
    Returns:
        Formatted time string (e.g., "~5:30")
    """
    if position_in_queue == 0:
        # Next song
        return f"~{format_duration(current_song_remaining)}"
    
    # Calculate total duration of songs before this one
    total_seconds = current_song_remaining
    
    for i in range(position_in_queue):
        if i < len(queue_songs):
            duration = queue_songs[i].get('duration', 0)
            if duration:
                total_seconds += duration
            else:
                # Unknown duration, estimate 3 minutes
                total_seconds += 180
    
    return f"~{format_duration(total_seconds)}"


def calculate_total_queue_duration(queue_songs: list) -> int:
    """
    Calculate total duration of all songs in queue
    
    Args:
        queue_songs: List of song dictionaries
    
    Returns:
        Total duration in seconds
    """
    total = 0
    for song in queue_songs:
        duration = song.get('duration', 0)
        if duration:
            total += duration
        else:
            # Unknown duration, estimate 3 minutes
            total += 180
    
    return total


def sanitize_url(url: str) -> Optional[str]:
    """
    Sanitize and validate URL
    
    Args:
        url: URL to sanitize
    
    Returns:
        Sanitized URL or None if invalid
    """
    if not url:
        return None
    
    url = url.strip()
    
    # Check if it's a valid HTTP(S) URL
    if not url.startswith(('http://', 'https://')):
        return None
    
    # Basic length check
    if len(url) > 2048:
        return None
    
    # Check for common video platforms
    valid_domains = [
        'youtube.com',
        'youtu.be',
        'soundcloud.com',
        'spotify.com',
        'twitch.tv',
    ]
    
    # If it contains a known domain, it's probably valid
    # Otherwise, let yt-dlp handle validation
    return url


def get_user_display_name(user) -> str:
    """
    Get the display name of a user
    
    Args:
        user: Discord user object
    
    Returns:
        Display name string
    """
    if hasattr(user, 'display_name'):
        return user.display_name
    elif hasattr(user, 'name'):
        return user.name
    else:
        return "Unknown User"


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Truncate a string to a maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        Truncated string
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_number(num: int) -> str:
    """
    Format a number with thousand separators
    
    Args:
        num: Number to format
    
    Returns:
        Formatted string
    """
    return f"{num:,}"


def get_emoji_for_position(position: int) -> str:
    """
    Get an emoji for a queue position
    
    Args:
        position: Position in queue (1-indexed)
    
    Returns:
        Emoji string
    """
    emoji_numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    if 1 <= position <= 10:
        return emoji_numbers[position - 1]
    
    return f"{position}."
