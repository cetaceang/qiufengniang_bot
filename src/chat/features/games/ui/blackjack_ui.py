import discord
from discord.ui import View, button, Button

class BlackjackView(View):
    def __init__(self, game_cog, game_instance):
        super().__init__(timeout=180)
        self.game_cog = game_cog
        self.game_instance = game_instance
        self.update_buttons()

    def update_buttons(self):
        """根据游戏状态更新按钮"""
        if self.game_instance.game_over:
            for item in self.children:
                item.disabled = True
        else:
            # 玩家点数超过21点时禁用要牌按钮
            player_value = self.game_instance.calculate_hand_value(self.game_instance.player_hand)
            self.hit_button.disabled = player_value >= 21

    @button(label="要牌 (Hit)", style=discord.ButtonStyle.primary, custom_id="hit")
    async def hit_button(self, interaction: discord.Interaction, button: Button):
        await self.game_cog.handle_hit(interaction)

    @button(label="停牌 (Stand)", style=discord.ButtonStyle.secondary, custom_id="stand")
    async def stand_button(self, interaction: discord.Interaction, button: Button):
        await self.game_cog.handle_stand(interaction)