import discord
from discord.ext import commands
from discord import app_commands

from src.chat.features.games.services.blackjack_service import BlackjackService
from src.chat.features.games.ui.blackjack_ui import BlackjackView
from src.chat.features.games.ui.bet_modal import BetModal
from src.chat.features.odysseia_coin.service.coin_service import coin_service
from src.chat.features.games.config.text_config import text_config as TextConfig

class BlackjackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        self.coin_service = coin_service

    # @app_commands.command(name="blackjack", description=TextConfig.BLACKJACK_DESCRIPTION)
    # async def blackjack(self, interaction: discord.Interaction):
    #     user_id = interaction.user.id
    #     if user_id in self.active_games:
    #         await interaction.response.send_message(TextConfig.BLACKJACK_ALREADY_STARTED, ephemeral=True)
    #         return

    #     modal = BetModal(title="21点下注")
    #     await interaction.response.send_modal(modal)
    #     await modal.wait()

    #     if not modal.is_submitted():
    #         return

    #     bet_amount = modal.amount
    #     new_balance = await self.coin_service.remove_coins(user_id, bet_amount, "21点下注")
    #     if new_balance is None:
    #         await interaction.followup.send(TextConfig.GHOST_CARD_NOT_ENOUGH_COINS.format(bet_amount=bet_amount), ephemeral=True)
    #         return

    #     game = BlackjackService(self.bot, user_id, bet_amount)
    #     game.start_game()
    #     self.active_games[user_id] = game

    #     view = BlackjackView(self, game)
    #     embed = self.create_game_embed(game)
        
    #     await interaction.followup.send(embed=embed, view=view)

    def create_game_embed(self, game: BlackjackService, show_dealer_card: bool = False) -> discord.Embed:
        state = game.get_game_state(show_dealer_card)
        player_hand_str = " ".join(state["player_hand"])
        dealer_hand_str = " ".join(state["dealer_hand"])

        embed = discord.Embed(title="21点游戏", color=discord.Color.gold())
        embed.add_field(name=f"你的手牌 ({state['player_value']})", value=player_hand_str, inline=False)
        embed.add_field(name=f"庄家的手牌 ({state['dealer_value']})", value=dealer_hand_str, inline=False)

        if state["game_over"]:
            result_text, color = self.get_result_text_and_color(state["result"], game.bet_amount)
            embed.description = result_text
            embed.color = color
        
        return embed

    def get_result_text_and_color(self, result: str, bet_amount: int):
        if result == "player_bust":
            return TextConfig.BLACKJACK_PLAYER_BUST.format(bet_amount=bet_amount), discord.Color.red()
        elif result == "dealer_bust":
            return TextConfig.BLACKJACK_DEALER_BUST.format(bet_amount=bet_amount * 2), discord.Color.green()
        elif result == "player_win":
            return TextConfig.BLACKJACK_PLAYER_WIN.format(bet_amount=bet_amount * 2), discord.Color.green()
        elif result == "dealer_win":
            return TextConfig.BLACKJACK_DEALER_WIN.format(bet_amount=bet_amount), discord.Color.red()
        elif result == "push":
            return TextConfig.BLACKJACK_PUSH, discord.Color.light_grey()
        return "", discord.Color.default()

    async def handle_hit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        game = self.active_games.get(user_id)
        if not game:
            await interaction.response.send_message(TextConfig.BLACKJACK_NO_GAME_FOUND, ephemeral=True)
            return

        game.player_hit()
        
        if game.game_over:
            await self.end_game(interaction, game)
        else:
            view = BlackjackView(self, game)
            embed = self.create_game_embed(game)
            await interaction.response.edit_message(embed=embed, view=view)

    async def handle_stand(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        game = self.active_games.get(user_id)
        if not game:
            await interaction.response.send_message(TextConfig.BLACKJACK_NO_GAME_FOUND, ephemeral=True)
            return

        await interaction.response.defer()
        await game.dealer_turn()
        await self.end_game(interaction, game, deferred=True)

    async def end_game(self, interaction: discord.Interaction, game: BlackjackService, deferred: bool = False):
        user_id = interaction.user.id
        result = game.get_result()
        
        if result in ["dealer_bust", "player_win"]:
            await self.coin_service.add_coins(user_id, game.bet_amount * 2, "21点胜利")
        elif result == "push":
            await self.coin_service.add_coins(user_id, game.bet_amount, "21点平局返还")

        view = BlackjackView(self, game)
        view.update_buttons()
        embed = self.create_game_embed(game, show_dealer_card=True)
        
        if deferred:
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        
        if user_id in self.active_games:
            del self.active_games[user_id]

async def setup(bot):
    await bot.add_cog(BlackjackCog(bot))