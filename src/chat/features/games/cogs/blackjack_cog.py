# -*- coding: utf-8 -*-

import discord
from discord import app_commands
from discord.ext import commands
import logging

from src.chat.features.games.ui.bet_view import BetView
from src.chat.features.games.ui.blackjack_ui import BlackjackView
from src.chat.features.games.services.blackjack_service import GameStatus

log = logging.getLogger(__name__)

class BlackjackCog(commands.Cog):
    """21点游戏命令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="开始一局21点游戏")
    async def blackjack(self, interaction: discord.Interaction):
        """处理 /blackjack 命令"""
        try:
            # 使用 BetView 让用户下注
            bet_view = BetView(
                user=interaction.user,
                guild_id=interaction.guild.id,
                game_starter=self.start_blackjack_game
            )
            
            embed = discord.Embed(
                title="🎲 21点",
                description="请输入你的赌注。",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=bet_view, ephemeral=True)

        except Exception as e:
            log.error(f"开启21点游戏失败: {e}", exc_info=True)
            await interaction.response.send_message("抱歉，开始游戏时遇到问题。", ephemeral=True)

    async def start_blackjack_game(self, interaction: discord.Interaction, bet_amount: int):
        """下注后，实际开始游戏的回调函数"""
        try:
            user = interaction.user
            guild_id = interaction.guild.id
            
            # 创建并发送游戏视图
            game_view = BlackjackView(user, guild_id, bet_amount)
            
            initial_embed = game_view.create_embed("21点游戏开始！")
            
            # 检查开局是否即为黑杰克
            game_state = game_view.get_game_state(game_view.game_id)
            if game_state["status"] == GameStatus.PLAYER_BLACKJACK:
                initial_embed.title = "Blackjack! 你赢了！"
                for item in game_view.children:
                    item.disabled = True
            
            await interaction.response.send_message(embed=initial_embed, view=game_view)
            game_view.message = await interaction.original_response()

        except Exception as e:
            log.error(f"启动21点游戏视图失败: {e}", exc_info=True)
            await interaction.followup.send("启动游戏视图时出错。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BlackjackCog(bot))