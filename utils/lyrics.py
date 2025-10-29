# -*- coding: utf-8 -*-
"""
Lyrics fetching utility for Discord Music Bot
"""

import aiohttp
import logging
from typing import Optional, Dict
from urllib.parse import quote


logger = logging.getLogger('discord.lyrics')


class LyricsProvider:
    """
    Fetches lyrics from various APIs
    """
    
    def __init__(self, api_url: str = "https://api.lyrics.ovh/v1"):
        """
        Initialize lyrics provider
        
        Args:
            api_url: Base URL for lyrics API
        """
        self.api_url = api_url
    
    async def fetch_lyrics(self, artist: str, title: str) -> Optional[str]:
        """
        Fetch lyrics for a song
        
        Args:
            artist: Artist name
            title: Song title
        
        Returns:
            Lyrics text or None if not found
        """
        try:
            url = f"{self.api_url}/{quote(artist)}/{quote(title)}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('lyrics')
                    elif response.status == 404:
                        logger.info(f"Lyrics not found for {artist} - {title}")
                        return None
                    else:
                        logger.warning(f"Lyrics API returned status {response.status}")
                        return None
        
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching lyrics: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching lyrics: {e}", exc_info=True)
            return None
    
    async def search_lyrics(self, query: str) -> Optional[str]:
        """
        Search for lyrics by query (attempts to parse artist and title)
        
        Args:
            query: Search query (e.g., "artist - title" or "title")
        
        Returns:
            Lyrics text or None if not found
        """
        # Try to split artist and title
        if ' - ' in query:
            parts = query.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        elif ' by ' in query.lower():
            parts = query.lower().split(' by ', 1)
            title = parts[0].strip()
            artist = parts[1].strip()
        else:
            # Can't determine artist, use query as title
            # This will likely not find lyrics, but we try anyway
            artist = "Unknown"
            title = query.strip()
        
        return await self.fetch_lyrics(artist, title)
    
    @staticmethod
    def format_lyrics(lyrics: str, max_length: int = 2000) -> list:
        """
        Format lyrics into chunks that fit in Discord embeds
        
        Args:
            lyrics: Full lyrics text
            max_length: Maximum length per chunk
        
        Returns:
            List of lyric chunks
        """
        if not lyrics:
            return []
        
        # Split by paragraphs first
        paragraphs = lyrics.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, start new chunk
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # If still no chunks (single line too long), split by lines
        if not chunks and lyrics:
            lines = lyrics.split('\n')
            current_chunk = ""
            
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        return chunks if chunks else [lyrics[:max_length]]
    
    @staticmethod
    def extract_artist_title_from_youtube(youtube_title: str) -> tuple:
        """
        Attempt to extract artist and title from a YouTube video title
        
        Args:
            youtube_title: YouTube video title
        
        Returns:
            Tuple of (artist, title)
        """
        # Remove common patterns
        cleaned = youtube_title
        
        # Remove things in brackets/parentheses
        patterns_to_remove = [
            r'\[.*?\]',  # [Official Video]
            r'\(.*?[Oo]fficial.*?\)',  # (Official Music Video)
            r'\(.*?[Ll]yrics.*?\)',  # (Lyrics)
            r'\(.*?[Aa]udio.*?\)',  # (Official Audio)
            r'\s*-\s*Topic$',  # - Topic at the end
        ]
        
        import re
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned)
        
        cleaned = cleaned.strip()
        
        # Try to split by common separators
        separators = [' - ', ' – ', ' | ', ' • ']
        for sep in separators:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                artist = parts[0].strip()
                title = parts[1].strip()
                return (artist, title)
        
        # If no separator found, use whole title
        return ("Unknown", cleaned)
