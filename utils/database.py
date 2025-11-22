import redis
import json
import os
import logging

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

    # --- Queue Persistence ---
    # Note: Storing complex song objects might be tricky. 
    # We'll store a list of dicts representing the songs.
    def save_queue(self, guild_id, queue):
        if not self.client: return
        # Queue items are already dicts from yt_dlp
        self.client.set(f"queue:{guild_id}", json.dumps(queue))

    def load_queue(self, guild_id):
        if not self.client: return []
        data = self.client.get(f"queue:{guild_id}")
        return json.loads(data) if data else []
    
    def clear_queue(self, guild_id):
        if not self.client: return
        self.client.delete(f"queue:{guild_id}")

    # --- Cache ---
    def cache_get(self, key):
        if not self.client: return None
        val = self.client.get(f"cache:{key}")
        return json.loads(val) if val else None

    def cache_set(self, key, value, ttl=3600):
        if not self.client: return
        self.client.setex(f"cache:{key}", ttl, json.dumps(value))
