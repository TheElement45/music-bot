# -*- coding: utf-8 -*-
"""
Music cog package
"""

from .commands import MusicCommands

__all__ = ['MusicCommands']


async def setup(bot):
    """Load the music cog"""
    await bot.add_cog(MusicCommands(bot))
