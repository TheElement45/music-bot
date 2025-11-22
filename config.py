# -*- coding: utf-8 -*-
"""
Configuration file for Discord Music Bot
All configurable settings are centralized here
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== Bot Configuration ======
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "-")

# ====== Music Configuration ======
# Maximum queue size per guild (0 = unlimited)
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "100"))

# Maximum song duration in seconds (0 = unlimited)
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "600"))  # 10 minutes default

# Default volume (0-100)
DEFAULT_VOLUME = int(os.getenv("DEFAULT_VOLUME", "75"))

# Auto-disconnect timeout (seconds when alone in VC)
AUTO_DISCONNECT_TIMEOUT = int(os.getenv("AUTO_DISCONNECT_TIMEOUT", "120"))

# ====== Cache Configuration ======
# Cache TTL for song metadata (seconds)
METADATA_CACHE_TTL = int(os.getenv("METADATA_CACHE_TTL", "3600"))  # 1 hour

# Cache TTL for stream URLs (seconds)
STREAM_URL_CACHE_TTL = int(os.getenv("STREAM_URL_CACHE_TTL", "300"))  # 5 minutes

# Maximum cache size (number of items)
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "500"))

# ====== History Configuration ======
# Maximum history size per guild
MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", "50"))

# ====== Rate Limiting ======
# Commands per user per minute
RATE_LIMIT_COMMANDS = int(os.getenv("RATE_LIMIT_COMMANDS", "5"))

# Rate limit window (seconds)
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ====== Permissions ======
# DJ role name (leave empty to disable DJ role requirement)
DJ_ROLE_NAME = os.getenv("DJ_ROLE_NAME", "")

# Allow users to bypass DJ requirement if alone with bot
ALONE_BYPASS_DJ = os.getenv("ALONE_BYPASS_DJ", "True").lower() == "true"

# ====== yt-dlp Configuration ======
YDL_BASE_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'skip_download': True,
    'socket_timeout': 30,
}

# ====== FFmpeg Configuration ======
def get_ffmpeg_options(volume: float = 1.0, filter_name: str = 'off'):
    """
    Generate FFmpeg options with dynamic audio filters
    
    Args:
        volume: Volume level (0.0-1.0)
        filter_name: Name of the filter ('off', 'nightcore', 'vaporwave', 'bassboost', '8d')
    
    Returns:
        dict: FFmpeg options
    """
    # Base volume filter
    filters = [f"volume={volume}"]
    
    # Pre-defined filters
    # Note: asetrate changes both speed and pitch. aresample restores sample rate for Discord.
    filter_map = {
        'off': [],
        'nightcore': ['asetrate=48000*1.25', 'aresample=48000'],
        'vaporwave': ['asetrate=48000*0.8', 'aresample=48000'],
        'bassboost': ['bass=g=20'],
        '8d': ['apulsator=hz=0.125'],
        'karaoke': ['stereotools=mlev=0.03']
    }
    
    if filter_name in filter_map:
        filters.extend(filter_map[filter_name])
    
    filter_string = ','.join(filters)
    
    return {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': f'-vn -filter:a "{filter_string}"'
    }

# Default FFmpeg options
FFMPEG_OPTIONS = get_ffmpeg_options()

# ====== Embed Colors ======
COLOR_PLAYING = 0x00FF00  # Green
COLOR_QUEUED = 0x0099FF   # Blue
COLOR_ERROR = 0xFF0000    # Red
COLOR_INFO = 0xFFFF00     # Yellow

# ====== Logging Configuration ======
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/discord.log")
LOG_ROTATION = os.getenv("LOG_ROTATION", "midnight")  # midnight, H, D, W0-W6
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))

# ====== Feature Flags ======
ENABLE_LYRICS = os.getenv("ENABLE_LYRICS", "True").lower() == "true"
ENABLE_VOTE_SKIP = os.getenv("ENABLE_VOTE_SKIP", "True").lower() == "true"
VOTE_SKIP_THRESHOLD = float(os.getenv("VOTE_SKIP_THRESHOLD", "0.5"))  # 50%

# ====== API Configuration ======
# Lyrics API (using lyrics.ovh as default)
LYRICS_API_URL = os.getenv("LYRICS_API_URL", "https://api.lyrics.ovh/v1")
