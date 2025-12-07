# -*- coding: utf-8 -*-
"""
Embed builders for music bot
"""

import discord
from typing import Optional, List

import config
from models.song import Song
from utils.helpers import format_duration, create_progress_bar, calculate_total_queue_duration


class EmbedBuilder:
    """Factory for creating music-related embeds"""
    
    @staticmethod
    def now_playing(song: Song) -> discord.Embed:
        """Create now playing embed"""
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{song.title}]({song.webpage_url})",
            color=config.COLOR_SUCCESS
        )
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        if song.duration:
            embed.add_field(name="Duration", value=song.formatted_duration, inline=True)
        
        if song.uploader:
            embed.add_field(name="Channel", value=song.uploader, inline=True)
        
        return embed
    
    @staticmethod
    def now_playing_detailed(
        song: Song,
        elapsed: int,
        loop_mode: str,
        volume: float,
        queue_length: int
    ) -> discord.Embed:
        """Create detailed now playing embed with progress"""
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{song.title}]({song.webpage_url})",
            color=config.COLOR_PLAYING
        )
        
        # Progress bar
        progress_bar = create_progress_bar(elapsed, song.duration, length=15)
        embed.add_field(
            name="Progress",
            value=f"{progress_bar}\n`{format_duration(elapsed)} / {song.formatted_duration}`",
            inline=False
        )
        
        # Loop mode
        loop_emoji = {'off': '🚫', 'song': '🔂', 'queue': '🔁'}.get(loop_mode, '🚫')
        embed.add_field(name="Loop", value=f"{loop_emoji} {loop_mode.capitalize()}", inline=True)
        
        # Volume
        embed.add_field(name="Volume", value=f"🔊 {int(volume * 100)}%", inline=True)
        
        # Queue length
        embed.add_field(name="Queue", value=f"📋 {queue_length} songs", inline=True)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        return embed
    
    @staticmethod
    def queue(
        current: Optional[Song],
        queue: List[Song],
        page: int,
        total_pages: int
    ) -> discord.Embed:
        """Create queue embed with pagination"""
        embed = discord.Embed(title="🎵 Music Queue", color=config.COLOR_INFO)
        
        # Now playing
        if current:
            embed.add_field(
                name="Now Playing",
                value=f"[{current.title}]({current.webpage_url})\n`{current.formatted_duration}`",
                inline=False
            )
        
        # Queue items
        if queue:
            items_per_page = 10
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            
            queue_text = ""
            for i, song in enumerate(queue[start_idx:end_idx], start=start_idx + 1):
                title = song.title[:40] + "..." if len(song.title) > 40 else song.title
                queue_text += f"`{i}.` {title} `{song.formatted_duration}`\n"
            
            embed.add_field(
                name=f"Up Next ({len(queue)} songs)",
                value=queue_text or "Empty",
                inline=False
            )
            
            # Total duration
            total_duration = calculate_total_queue_duration([s.to_dict() for s in queue])
            embed.set_footer(text=f"Page {page}/{total_pages} • Total: {format_duration(total_duration)}")
        else:
            embed.add_field(name="Queue", value="Empty", inline=False)
        
        return embed
    
    @staticmethod
    def added_to_queue(song: Song, position: int) -> discord.Embed:
        """Create 'added to queue' embed"""
        embed = discord.Embed(
            title="➕ Added to Queue",
            description=f"[{song.title}]({song.webpage_url})",
            color=config.COLOR_QUEUED
        )
        embed.add_field(name="Position", value=f"#{position}", inline=True)
        embed.add_field(name="Duration", value=song.formatted_duration, inline=True)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        return embed
    
    @staticmethod
    def added_playlist(count: int, more_loading: bool = False) -> discord.Embed:
        """Create 'added playlist' embed"""
        description = f"Added **{count}** songs to queue"
        if more_loading:
            description += "\n*Loading more songs in background...*"
        
        return discord.Embed(
            title="📋 Playlist Added",
            description=description,
            color=config.COLOR_QUEUED
        )
    
    @staticmethod
    def lyrics(query: str, lyrics_text: str, page: int = 1, total_pages: int = 1) -> discord.Embed:
        """Create lyrics embed"""
        title = f"📝 Lyrics: {query}"
        if total_pages > 1:
            title = f"📝 Lyrics: {query} ({page}/{total_pages})"
        
        return discord.Embed(
            title=title,
            description=lyrics_text,
            color=config.COLOR_INFO
        )
    
    @staticmethod
    def error(message: str) -> discord.Embed:
        """Create error embed"""
        return discord.Embed(
            title="❌ Error",
            description=message,
            color=config.COLOR_ERROR
        )
    
    @staticmethod
    def stats(
        uptime: str,
        guild_count: int,
        voice_connections: int,
        total_queued: int,
        cache_stats: dict
    ) -> discord.Embed:
        """Create bot stats embed"""
        embed = discord.Embed(title="📊 Bot Statistics", color=config.COLOR_INFO)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Voice Connections", value=str(voice_connections), inline=True)
        embed.add_field(name="Total Queued Songs", value=str(total_queued), inline=True)
        
        if 'metadata' in cache_stats:
            meta = cache_stats['metadata']
            embed.add_field(
                name="Cache Performance",
                value=f"Hit Rate: {meta['hit_rate']}\nCached: {meta['size']}/{meta['max_size']}",
                inline=False
            )
        
        return embed
