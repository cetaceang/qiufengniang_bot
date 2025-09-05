import random
import asyncio
from typing import List, Dict, Union

# 定义牌的点数
CARD_VALUES = {
    'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10
}
# 定义牌的种类
SUITS = ['♠', '♥', '♦', '♣']
# 定义所有牌
DECKS = [f'{suit}{rank}' for suit in SUITS for rank, value in CARD_VALUES.items()]

class BlackjackService:
    def __init__(self, bot, user_id, bet_amount):
        self.bot = bot
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.deck = random.sample(DECKS, len(DECKS))
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False

    def deal_card(self, hand: List[str]) -> None:
        """发一张牌到指定手牌"""
        card = self.deck.pop()
        hand.append(card)

    def calculate_hand_value(self, hand: List[str]) -> int:
        """计算手牌的点数"""
        value = 0
        aces = 0
        for card in hand:
            rank = card[1:]
            value += CARD_VALUES[rank]
            if rank == 'A':
                aces += 1
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def start_game(self):
        """开始游戏，给玩家和庄家各发两张牌"""
        self.deal_card(self.player_hand)
        self.deal_card(self.dealer_hand)
        self.deal_card(self.player_hand)
        self.deal_card(self.dealer_hand)

    def player_hit(self):
        """玩家要牌"""
        self.deal_card(self.player_hand)
        if self.calculate_hand_value(self.player_hand) > 21:
            self.game_over = True

    async def dealer_turn(self):
        """庄家回合"""
        while self.calculate_hand_value(self.dealer_hand) < 17:
            await asyncio.sleep(1)
            self.deal_card(self.dealer_hand)
        self.game_over = True

    def get_game_state(self, show_dealer_card: bool = False) -> Dict[str, Union[List[str], int, str]]:
        """获取当前游戏状态"""
        player_value = self.calculate_hand_value(self.player_hand)
        dealer_value = self.calculate_hand_value(self.dealer_hand)
        
        if show_dealer_card:
            dealer_hand_display = self.dealer_hand
            dealer_value_display = dealer_value
        else:
            dealer_hand_display = [self.dealer_hand[0], '??']
            dealer_value_display = self.calculate_hand_value([self.dealer_hand[0]])

        return {
            "player_hand": self.player_hand,
            "player_value": player_value,
            "dealer_hand": dealer_hand_display,
            "dealer_value": dealer_value_display,
            "game_over": self.game_over,
            "result": self.get_result() if self.game_over else None
        }

    def get_result(self) -> str:
        """判断游戏结果"""
        player_value = self.calculate_hand_value(self.player_hand)
        dealer_value = self.calculate_hand_value(self.dealer_hand)

        if player_value > 21:
            return "player_bust"
        if dealer_value > 21:
            return "dealer_bust"
        if player_value > dealer_value:
            return "player_win"
        if dealer_value > player_value:
            return "dealer_win"
        return "push"