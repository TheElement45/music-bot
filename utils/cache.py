# -*- coding: utf-8 -*-
"""
Caching utilities for the Discord Music Bot
"""

import time
import json
import asyncio
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
from .database import RedisManager
import os

class SimpleCache:
    """
    Cache implementation that uses Redis if available, falling back to in-memory.
    """
    
    def __init__(self, max_size: int = 500, namespace: str = "cache"):
        """
        Initialize the cache
        
        Args:
            max_size: Maximum number of items to store (for in-memory fallback)
            namespace: Redis key prefix
        """
        self.max_size = max_size
        self.namespace = namespace
        self.redis = RedisManager(host=os.getenv('REDIS_HOST', 'redis'))
        
        # In-memory fallback
        self._cache: OrderedDict[str, Tuple[Any, float, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache
        """
        # Try Redis first
        if self.redis.is_connected():
            val = self.redis.cache_get(f"{self.namespace}:{key}")
            if val is not None:
                self._hits += 1
                return val
            self._misses += 1
            return None

        # Fallback to in-memory
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expiry, _ = self._cache[key]
            
            if expiry and time.time() > expiry:
                del self._cache[key]
                self._misses += 1
                return None
            
            self._cache.move_to_end(key)
            self._hits += 1
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set a value in the cache
        """
        # Try Redis first
        if self.redis.is_connected():
            # RedisManager.cache_set expects key without prefix if we use it directly, 
            # but here we want to manage the namespace ourselves or let RedisManager handle it.
            # Looking at database.py, cache_set does: client.setex(f"cache:{key}", ...)
            # So we should pass the key relative to "cache".
            # However, we want different namespaces (metadata, lyrics, etc).
            # Let's use the raw client if we want custom keys, or just use a prefix in the key passed to cache_set.
            # Actually, database.py has `cache_set(key, value, ttl)` which prefixes with `cache:`.
            # To support sub-namespaces like `cache:metadata:`, we can pass `metadata:key`.
            
            full_key = f"{self.namespace}:{key}"
            self.redis.cache_set(full_key, value, ttl=ttl if ttl else 3600)
            return

        # Fallback to in-memory
        async with self._lock:
            expiry = time.time() + ttl if ttl else None
            created = time.time()
            
            if key in self._cache:
                self._cache[key] = (value, expiry, created)
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                
                self._cache[key] = (value, expiry, created)
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache
        """
        if self.redis.is_connected():
            # We can't easily delete via RedisManager wrapper as it lacks delete for cache.
            # We'll access the client directly if needed or add a method to RedisManager.
            # For now, let's assume we can't delete easily or just ignore it for Redis 
            # (TTL will handle it), OR we can use the raw client.
            if self.redis.client:
                return bool(self.redis.client.delete(f"cache:{self.namespace}:{key}"))
            return False

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self):
        """
        Clear all items from the cache
        """
        if self.redis.is_connected():
            # Clearing specific namespace in Redis is hard without SCAN.
            # We'll skip clearing Redis for now to avoid blocking, or implement SCAN later.
            pass

        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    async def cleanup_expired(self):
        """
        Remove all expired items from the cache
        """
        # Redis handles this automatically.
        if self.redis.is_connected():
            return

        async with self._lock:
            current_time = time.time()
            keys_to_delete = []
            
            for key, (_, expiry, _) in self._cache.items():
                if expiry and current_time > expiry:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._cache[key]
    
    def size(self) -> int:
        if self.redis.is_connected():
            return 0 # Unknown
        return len(self._cache)
    
    def get_stats(self) -> Dict[str, Any]:
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': self.size(),
            'max_size': self.max_size,
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total_requests,
            'hit_rate': f"{hit_rate:.1f}%",
            'backend': 'redis' if self.redis.is_connected() else 'memory'
        }
    
    async def get_or_set(self, key: str, factory, ttl: Optional[int] = None) -> Any:
        value = await self.get(key)
        
        if value is not None:
            return value
        
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.set(key, value, ttl)
        return value


class GuildCache:
    """
    Per-guild cache manager
    """
    
    def __init__(self, max_size: int = 500):
        self.metadata_cache = SimpleCache(max_size, namespace="metadata")
        self.stream_url_cache = SimpleCache(max_size, namespace="stream")
        self.lyrics_cache = SimpleCache(max_size // 2, namespace="lyrics")
    
    async def cleanup_all(self):
        await self.metadata_cache.cleanup_expired()
        await self.stream_url_cache.cleanup_expired()
        await self.lyrics_cache.cleanup_expired()
    
    async def clear_all(self):
        await self.metadata_cache.clear()
        await self.stream_url_cache.clear()
        await self.lyrics_cache.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            'metadata': self.metadata_cache.get_stats(),
            'stream_urls': self.stream_url_cache.get_stats(),
            'lyrics': self.lyrics_cache.get_stats()
        }
