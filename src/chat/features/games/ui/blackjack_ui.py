# -*- coding: utf-8 -*-

import discord
import logging
from typing import List

from src.chat.features.games.services.blackjack_service import blackjack_service, GameStatus
from src.chat.features.odysseia_coin.service.coin_service import coin_service
from .bet_view import BetView
from ..services.card import Card

log = logging.getLogger(__name__)

class BlackjackView(discord.ui.View):
    """21点游戏界面"""

    def __init__(self, user: discord.User, guild_id: int, bet_amount: int):
        super().__init__(timeout=180)
        self.user = user
        self.guild_id = guild_id
        self.bet_amount = bet_amount
        self.game_id = blackjack_service.start_game(user.id, guild_id, bet_amount)
        self.message: discord.Message = None

    async def on_timeout(self):
        game_state = blackjack_service.get_game_state(self.game_id)
        if game_state and game_state["status"] == GameStatus.IN_PROGRESS:
            # 游戏超时，视为玩家弃牌，输掉赌注
            await coin_service.add_coins(self.user.id, self.guild_id, -self.bet_amount)
            for item in self.children:
                item.disabled = True
            embed = self.create_embed("游戏超时，你输了！")
            await self.message.edit(embed=embed, view=self)
        blackjack_service.end_game(self.game_id)

    def create_embed(self, title: str) -> discord.Embed:
        """创建游戏状态的Embed"""
        game_state = blackjack_service.get_game_state(self.game_id)
        if not game_state:
            return discord.Embed(title="错误", description="游戏状态未找到。", color=discord.Color.red())

        player_hand_str = " ".join(str(card) for card in game_state["player_hand"])
        player_score = game_state["player_score"]
        
        dealer_hand_str = " ".join(str(card) for card in game_state["dealer_hand"])
        dealer_score = game_state["dealer_score"]

        # 在游戏进行中，只显示庄家的一张牌
        if game_state["status"] == GameStatus.IN_PROGRESS:
            dealer_hand_str = f"{str(game_state['dealer_hand'][0])} ❓"
            dealer_score = "?"

        embed = discord.Embed(title=title, color=discord.Color.green())
        embed.add_field(name=f"{self.user.display_name}的手牌 ({player_score})", value=player_hand_str, inline=False)
        embed.add_field(name=f"庄家的手牌 ({dealer_score})", value=dealer_hand_str, inline=False)
        embed.set_footer(text=f"赌注: {self.bet_amount} Odysseia Coin")
        
        return embed

    async def update_view(self, interaction: discord.Interaction, title: str):
        """更新视图和Embed"""
        embed = self.create_embed(title)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="要牌 (Hit)", style=discord.ButtonStyle.primary, custom_id="hit")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_state = blackjack_service.player_hit(self.game_id)
        if not game_state:
            await interaction.response.send_message("游戏不存在或已结束。", ephemeral=True)
            return

        if game_state["status"] != GameStatus.IN_PROGRESS:
            await self.end_game_actions(interaction)
        else:
            await self.update_view(interaction, "你的回合")

    @discord.ui.button(label="停牌 (Stand)", style=discord.ButtonStyle.success, custom_id="stand")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_state = blackjack_service.player_stand(self.game_id)
        if not game_state:
            await interaction.response.send_message("游戏不存在或已结束。", ephemeral=True)
            return
        
        await self.end_game_actions(interaction)

    @discord.ui.button(label="结束 (Quit)", style=discord.ButtonStyle.danger, custom_id="quit")
    async def quit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 提前结束游戏，视为认输
        game_state = blackjack_service.get_game_state(self.game_id)
        if game_state:
            winnings = -self.bet_amount
            await coin_service.add_coins(self.user.id, self.guild_id, winnings)
            title = f"你放弃了游戏，输掉了 {abs(winnings)} 金币。"
            for item in self.children:
                item.disabled = True
            embed = self.create_embed(title)
            await interaction.response.edit_message(embed=embed, view=self)
        
        blackjack_service.end_game(self.game_id)

    async def end_game_actions(self, interaction: discord.Interaction):
        """处理游戏结束时的通用逻辑"""
        game_state = blackjack_service.get_game_state(self.game_id)
        if not game_state:
            return

        status = game_state["status"]
        winnings = game_state["winnings"]
        
        result_messages = {
            GameStatus.PLAYER_WINS: f"你赢了 {winnings} 金币！",
            GameStatus.DEALER_WINS: f"你输了 {abs(winnings)} 金币。",
            GameStatus.PUSH: "平局，赌注已退回。",
            GameStatus.PLAYER_BLACKJACK: f"Blackjack! 你赢得了 {winnings} 金币！"
        }
        title = result_messages.get(status, "游戏结束")

        # 结算金币
        if winnings != 0:
            await coin_service.add_coins(self.user.id, self.guild_id, winnings)

        for item in self.children:
            item.disabled = True
        
        embed = self.create_embed(title)
        await interaction.response.edit_message(embed=embed, view=self)
        blackjack_service.end_game(self.game_id)