import redis
import json
import os
import logging
from typing import List, Optional, Dict

class RedisManager:
    def __init__(self, host='redis', port=6379, db=0):
        self.logger = logging.getLogger('music_bot.database')
        try:
            self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.client.ping()
            self.logger.info(f"Connected to Redis at {host}:{port}")
        except redis.ConnectionError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            self.client = None

    def is_connected(self):
        return self.client is not None

    # --- Settings ---
    def get_settings(self, guild_id):
        if not self.client: return {}
        data = self.client.get(f"settings:{guild_id}")
        return json.loads(data) if data else {}

    def set_setting(self, guild_id, key, value):
        if not self.client: return
        settings = self.get_settings(guild_id)
        settings[key] = value
        self.client.set(f"settings:{guild_id}", json.dumps(settings))

    def get_volume(self, guild_id):
        settings = self.get_settings(guild_id)
        return settings.get('volume', 1.0)

    def set_volume(self, guild_id, volume):
        self.set_setting(guild_id, 'volume', volume)

    def get_loop_mode(self, guild_id):
        settings = self.get_settings(guild_id)
        return settings.get('loop_mode', 'off')

    def set_loop_mode(self, guild_id, mode):
        self.set_setting(guild_id, 'loop_mode', mode)

    def get_filter(self, guild_id):
        settings = self.get_settings(guild_id)
        return settings.get('filter', 'off')

    def set_filter(self, guild_id, filter_name):
        self.set_setting(guild_id, 'filter', filter_name)

    # --- 24/7 Mode ---
    def get_247_mode(self, guild_id) -> bool:
        settings = self.get_settings(guild_id)
        return settings.get('is_247_mode', False)

    def set_247_mode(self, guild_id, enabled: bool):
        self.set_setting(guild_id, 'is_247_mode', enabled)

    # --- Auto-play ---
    def get_autoplay(self, guild_id) -> bool:
        settings = self.get_settings(guild_id)
        return settings.get('autoplay_enabled', False)

    def set_autoplay(self, guild_id, enabled: bool):
        self.set_setting(guild_id, 'autoplay_enabled', enabled)

    # --- Song Request Channel ---
    def get_request_channel(self, guild_id) -> Optional[int]:
        settings = self.get_settings(guild_id)
        return settings.get('request_channel_id')

    def set_request_channel(self, guild_id, channel_id: Optional[int]):
        self.set_setting(guild_id, 'request_channel_id', channel_id)

    # --- Queue Persistence ---
    def save_queue(self, guild_id, queue):
        if not self.client: return
        self.client.set(f"queue:{guild_id}", json.dumps(queue))

    def load_queue(self, guild_id):
        if not self.client: return []
        data = self.client.get(f"queue:{guild_id}")
        return json.loads(data) if data else []
    
    def clear_queue(self, guild_id):
        if not self.client: return
        self.client.delete(f"queue:{guild_id}")

    # --- Saved Playlists ---
    def save_playlist(self, guild_id, name: str, songs: List[dict]):
        """Save a playlist for a guild"""
        if not self.client: return
        key = f"playlists:{guild_id}"
        playlists = self.get_all_playlists(guild_id)
        playlists[name] = songs
        self.client.set(key, json.dumps(playlists))

    def load_playlist(self, guild_id, name: str) -> Optional[List[dict]]:
        """Load a saved playlist"""
        playlists = self.get_all_playlists(guild_id)
        return playlists.get(name)

    def delete_playlist(self, guild_id, name: str) -> bool:
        """Delete a saved playlist"""
        if not self.client: return False
        playlists = self.get_all_playlists(guild_id)
        if name in playlists:
            del playlists[name]
            self.client.set(f"playlists:{guild_id}", json.dumps(playlists))
            return True
        return False

    def get_all_playlists(self, guild_id) -> Dict[str, List[dict]]:
        """Get all saved playlists for a guild"""
        if not self.client: return {}
        data = self.client.get(f"playlists:{guild_id}")
        return json.loads(data) if data else {}

    def list_playlists(self, guild_id) -> List[str]:
        """List all playlist names for a guild"""
        return list(self.get_all_playlists(guild_id).keys())

    # --- Cache ---
    def cache_get(self, key):
        if not self.client: return None
        val = self.client.get(f"cache:{key}")
        return json.loads(val) if val else None

    def cache_set(self, key, value, ttl=3600):
        if not self.client: return
        self.client.setex(f"cache:{key}", ttl, json.dumps(value))
