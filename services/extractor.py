# -*- coding: utf-8 -*-
"""
Audio extractor service - wraps yt-dlp functionality
"""

import asyncio
import logging
import re
from typing import List, Optional, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp
from bs4 import BeautifulSoup

import config
from models.song import Song


logger = logging.getLogger('music_bot.extractor')

# URL patterns
YOUTUBE_URL_PATTERN = re.compile(
    r'(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)'
)
SPOTIFY_URL_PATTERN = re.compile(
    r'(https?://)?(open\.)?spotify\.com/(track|album|playlist|artist)/([a-zA-Z0-9]+)'
)


class ExtractorService:
    """Service for extracting audio info from URLs"""
    
    def __init__(self):
        self.logger = logger
    
    def _is_playlist_url(self, query: str) -> bool:
        """Check if URL is a playlist, mix, or radio"""
        query_lower = query.lower()
        # Check for playlist indicators
        if 'list=' in query_lower:
            return True
        if '/playlist' in query_lower:
            return True
        if '&list=' in query_lower or '?list=' in query_lower:
            return True
        # YouTube mix/radio
        if 'mix' in query_lower and 'youtube' in query_lower:
            return True
        return False
    
    async def extract(
        self, 
        query: str, 
        requester=None,
        max_playlist_items: int = 50
    ) -> Union[List[Song], dict]:
        """
        Extract song info from query (URL or search term)
        
        Args:
            query: URL or search query
            requester: Discord member who requested
            max_playlist_items: Max songs to extract from playlist initially
            
        Returns:
            List of Song objects, or dict with 'error' key on failure
        """
        # Handle Spotify URLs
        if SPOTIFY_URL_PATTERN.search(query):
            return await self._handle_spotify(query, requester)
        
        ydl_opts = config.YDL_BASE_OPTIONS.copy()
        is_playlist = self._is_playlist_url(query)
        
        if is_playlist:
            ydl_opts['extract_flat'] = 'in_playlist'  # Better for large playlists
            ydl_opts['noplaylist'] = False
            ydl_opts['playlistend'] = max_playlist_items
        else:
            ydl_opts['extract_flat'] = False
            ydl_opts['noplaylist'] = True
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False)
                
                if info is None:
                    return {'error': 'Could not extract info from URL'}
                
                if 'entries' in info:
                    # Playlist/mix
                    songs = []
                    for entry in info['entries']:
                        if entry:  # Skip None entries (hidden videos)
                            songs.append(Song.from_ytdl_info(entry, requester))
                    
                    if not songs:
                        return {'error': 'No playable videos found in playlist'}
                    return songs
                else:
                    # Single song
                    return [Song.from_ytdl_info(info, requester)]
                    
        except Exception as e:
            self.logger.error(f"YTDL error: {e}")
            
            # Smart search fallback - if URL failed, try searching
            if "http" in query:
                return await self._smart_search_fallback(query, requester)
            
            return {'error': str(e)}
    
    async def refresh_url(self, song: Song) -> Optional[Song]:
        """Re-extract stream URL for a song (when URL expired)"""
        url = song.webpage_url or song.original_url
        if not url:
            self.logger.error(f"Cannot refresh URL: no webpage_url for {song.title}")
            return None
        
        ydl_opts = config.YDL_BASE_OPTIONS.copy()
        ydl_opts['extract_flat'] = False
        ydl_opts['noplaylist'] = True
        
        try:
            self.logger.info(f"Refreshing stream URL for: {song.title}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                if info:
                    return Song.from_ytdl_info(info, song.requester)
                return None
        except Exception as e:
            self.logger.error(f"Error refreshing URL: {e}")
            return None
    
    async def search(self, query: str, requester=None, limit: int = 1) -> List[Song]:
        """Search YouTube for songs"""
        ydl_opts = config.YDL_BASE_OPTIONS.copy()
        ydl_opts['extract_flat'] = False
        ydl_opts['noplaylist'] = True
        
        search_query = f"ytsearch{limit}:{query}"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                
                if info and 'entries' in info and info['entries']:
                    return [Song.from_ytdl_info(entry, requester) for entry in info['entries'] if entry]
                return []
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return []
    
    async def get_related_songs(self, song: Song, limit: int = 5) -> List[Song]:
        """Get related/recommended songs based on current song (for auto-play)"""
        if not song.webpage_url:
            return []
        
        try:
            # Use YouTube's related videos feature
            # Search for similar songs based on title
            search_query = f"{song.title} similar songs"
            songs = await self.search(search_query, limit=limit)
            
            # Filter out the original song
            return [s for s in songs if s.webpage_url != song.webpage_url]
        except Exception as e:
            self.logger.error(f"Error getting related songs: {e}")
            return []
    
    async def extract_remaining_playlist(
        self, 
        playlist_url: str, 
        start_index: int,
        requester=None
    ) -> List[Song]:
        """Load remaining items from a playlist (background task)"""
        ydl_opts = config.YDL_BASE_OPTIONS.copy()
        ydl_opts['extract_flat'] = 'in_playlist'
        ydl_opts['noplaylist'] = False
        ydl_opts['playliststart'] = start_index + 1  # 1-indexed
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, playlist_url, download=False)
                
                if info and 'entries' in info and info['entries']:
                    return [Song.from_ytdl_info(entry, requester) for entry in info['entries'] if entry]
                return []
        except Exception as e:
            self.logger.error(f"Error loading remaining playlist: {e}")
            return []
    
    async def _smart_search_fallback(self, failed_query: str, requester=None) -> Union[List[Song], dict]:
        """Try searching when a URL fails"""
        self.logger.info(f"URL failed, trying smart search for: {failed_query}")
        
        songs = await self.search(failed_query, requester, limit=1)
        if songs:
            return songs
        return {'error': 'Could not find song'}
    
    async def _handle_spotify(self, url: str, requester=None) -> Union[List[Song], dict]:
        """Handle Spotify URLs by scraping track info and searching YouTube"""
        match = SPOTIFY_URL_PATTERN.search(url)
        if not match:
            return {'error': 'Invalid Spotify URL'}
        
        content_type = match.group(3)  # track, album, playlist, artist
        
        try:
            # Fetch Spotify page
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return {'error': f'Could not fetch Spotify page (status {resp.status})'}
                    html = await resp.text()
            
            soup = BeautifulSoup(html, 'lxml')
            
            if content_type == 'track':
                return await self._parse_spotify_track(soup, requester)
            elif content_type in ('album', 'playlist'):
                return await self._parse_spotify_playlist(soup, url, requester)
            else:
                return {'error': f'Spotify {content_type} URLs are not supported'}
                
        except asyncio.TimeoutError:
            return {'error': 'Spotify request timed out'}
        except Exception as e:
            self.logger.error(f"Spotify error: {e}")
            return {'error': f'Could not parse Spotify URL: {e}'}
    
    async def _parse_spotify_track(self, soup: BeautifulSoup, requester=None) -> Union[List[Song], dict]:
        """Parse a single Spotify track page"""
        # Try to find track info from meta tags
        title_tag = soup.find('meta', property='og:title')
        desc_tag = soup.find('meta', property='og:description')
        
        if not title_tag:
            return {'error': 'Could not find track info on Spotify page'}
        
        title = title_tag.get('content', '')
        # Description usually contains "Song · Artist"
        description = desc_tag.get('content', '') if desc_tag else ''
        
        # Build search query
        if description and '·' in description:
            parts = description.split('·')
            if len(parts) >= 2:
                artist = parts[1].strip()
                search_query = f"{title} {artist}"
            else:
                search_query = title
        else:
            search_query = title
        
        self.logger.info(f"Spotify track: searching YouTube for '{search_query}'")
        songs = await self.search(search_query, requester, limit=1)
        
        if songs:
            return songs
        return {'error': f'Could not find "{search_query}" on YouTube'}
    
    async def _parse_spotify_playlist(self, soup: BeautifulSoup, url: str, requester=None) -> Union[List[Song], dict]:
        """Parse a Spotify playlist/album page"""
        # Get playlist title
        title_tag = soup.find('meta', property='og:title')
        playlist_name = title_tag.get('content', 'Spotify Playlist') if title_tag else 'Spotify Playlist'
        
        # Find track listings (limited info from embed data)
        # Spotify pages embed JSON-LD data we can parse
        scripts = soup.find_all('script', type='application/ld+json')
        
        tracks = []
        for script in scripts:
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Album or playlist with track list
                    if 'track' in data:
                        track_list = data['track']
                        if isinstance(track_list, list):
                            for t in track_list[:20]:  # Limit to 20 tracks
                                if 'name' in t:
                                    artist = ''
                                    if 'byArtist' in t:
                                        artist_info = t['byArtist']
                                        if isinstance(artist_info, dict):
                                            artist = artist_info.get('name', '')
                                        elif isinstance(artist_info, list) and artist_info:
                                            artist = artist_info[0].get('name', '')
                                    tracks.append(f"{t['name']} {artist}".strip())
            except:
                continue
        
        if not tracks:
            return {'error': 'Could not parse tracks from Spotify playlist. Try individual track URLs.'}
        
        self.logger.info(f"Spotify playlist '{playlist_name}': found {len(tracks)} tracks")
        
        # Search YouTube for each track
        songs = []
        for track_query in tracks:
            result = await self.search(track_query, requester, limit=1)
            if result:
                songs.extend(result)
            await asyncio.sleep(0.5)  # Rate limiting
        
        if songs:
            return songs
        return {'error': 'Could not find any tracks on YouTube'}
