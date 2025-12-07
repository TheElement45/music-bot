# -*- coding: utf-8 -*-
"""
Discord UI components for music controls
"""

import discord
from typing import Optional


class MusicControlView(discord.ui.View):
    """Interactive music control buttons"""
    
    def __init__(self, cog, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.message: Optional[discord.Message] = None
    
    def _get_guild_id(self, interaction: discord.Interaction) -> Optional[int]:
        """Get guild ID from interaction"""
        if interaction.guild:
            return interaction.guild.id
        return None
    
    def update_buttons(self, guild_id: int):
        """Update button states based on playback state"""
        if not self.cog:
            return
        
        pause_button = discord.utils.get(self.children, custom_id="pause_resume")
        loop_button = discord.utils.get(self.children, custom_id="loop")
        
        if not pause_button or not loop_button:
            return
        
        # Update pause/resume button
        is_playing = self.cog.player.is_playing(guild_id)
        is_paused = self.cog.player.is_paused(guild_id)
        
        if is_paused:
            pause_button.emoji = '▶️'
            pause_button.style = discord.ButtonStyle.success
        elif is_playing:
            pause_button.emoji = '⏸️'
            pause_button.style = discord.ButtonStyle.secondary
        else:
            pause_button.emoji = '▶️'
            pause_button.style = discord.ButtonStyle.secondary
        
        # Update loop button
        loop_mode = self.cog.queue_service.get_loop_mode(guild_id)
        
        if loop_mode == 'song':
            loop_button.emoji = '🔂'
            loop_button.style = discord.ButtonStyle.success
        elif loop_mode == 'queue':
            loop_button.emoji = '🔁'
            loop_button.style = discord.ButtonStyle.success
        else:
            loop_button.emoji = '🚫'
            loop_button.style = discord.ButtonStyle.secondary
    
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="pause_resume")
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self._get_guild_id(interaction)
        if not guild_id:
            return
        
        if self.cog.player.is_playing(guild_id):
            self.cog.player.pause(guild_id)
        elif self.cog.player.is_paused(guild_id):
            self.cog.player.resume(guild_id)
        
        self.update_buttons(guild_id)
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self._get_guild_id(interaction)
        if guild_id:
            await self.cog.player.skip(guild_id)
    
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self._get_guild_id(interaction)
        if guild_id:
            self.cog.queue_service.clear(guild_id)
            await self.cog.player.skip(guild_id)
    
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self._get_guild_id(interaction)
        if not guild_id:
            return
        
        self.cog.queue_service.cycle_loop_mode(guild_id)
        self.update_buttons(guild_id)
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_id = self._get_guild_id(interaction)
        if guild_id:
            self.cog.queue_service.shuffle(guild_id)
