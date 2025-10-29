# -*- coding: utf-8 -*-
"""
Caching utilities for the Discord Music Bot
"""

import time
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
import asyncio


class SimpleCache:
    """
    Simple in-memory cache with TTL (Time To Live) support
    """
    
    def __init__(self, max_size: int = 500):
        """
        Initialize the cache
        
        Args:
            max_size: Maximum number of items to store
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, Tuple[Any, float, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found or expired
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expiry, _ = self._cache[key]
            
            # Check if expired
            if expiry and time.time() > expiry:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set a value in the cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None = no expiry)
        """
        async with self._lock:
            expiry = time.time() + ttl if ttl else None
            created = time.time()
            
            # If key exists, update it
            if key in self._cache:
                self._cache[key] = (value, expiry, created)
                self._cache.move_to_end(key)
            else:
                # Check if we need to evict oldest item
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)  # Remove oldest (first) item
                
                self._cache[key] = (value, expiry, created)
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache
        
        Args:
            key: Cache key
        
        Returns:
            True if key was found and deleted, False otherwise
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self):
        """
        Clear all items from the cache
        """
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    async def cleanup_expired(self):
        """
        Remove all expired items from the cache
        """
        async with self._lock:
            current_time = time.time()
            keys_to_delete = []
            
            for key, (_, expiry, _) in self._cache.items():
                if expiry and current_time > expiry:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._cache[key]
    
    def size(self) -> int:
        """
        Get the current size of the cache
        
        Returns:
            Number of items in cache
        """
        return len(self._cache)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache stats
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total_requests,
            'hit_rate': f"{hit_rate:.1f}%"
        }
    
    async def get_or_set(self, key: str, factory, ttl: Optional[int] = None) -> Any:
        """
        Get a value from cache, or set it using a factory function if not found
        
        Args:
            key: Cache key
            factory: Async function to call if key not found
            ttl: Time to live in seconds
        
        Returns:
            Cached or newly created value
        """
        value = await self.get(key)
        
        if value is not None:
            return value
        
        # Call factory function (can be async or sync)
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.set(key, value, ttl)
        return value


class GuildCache:
    """
    Per-guild cache manager
    Manages separate caches for different data types
    """
    
    def __init__(self, max_size: int = 500):
        """
        Initialize guild cache manager
        
        Args:
            max_size: Maximum size for each cache
        """
        self.metadata_cache = SimpleCache(max_size)
        self.stream_url_cache = SimpleCache(max_size)
        self.lyrics_cache = SimpleCache(max_size // 2)  # Smaller cache for lyrics
    
    async def cleanup_all(self):
        """
        Cleanup expired items from all caches
        """
        await self.metadata_cache.cleanup_expired()
        await self.stream_url_cache.cleanup_expired()
        await self.lyrics_cache.cleanup_expired()
    
    async def clear_all(self):
        """
        Clear all caches
        """
        await self.metadata_cache.clear()
        await self.stream_url_cache.clear()
        await self.lyrics_cache.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all caches
        
        Returns:
            Dictionary with stats for each cache
        """
        return {
            'metadata': self.metadata_cache.get_stats(),
            'stream_urls': self.stream_url_cache.get_stats(),
            'lyrics': self.lyrics_cache.get_stats()
        }
