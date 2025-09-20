# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum

from .card import Deck, Card

log = logging.getLogger(__name__)

class GameStatus(Enum):
    """游戏状态枚举"""
    IN_PROGRESS = "进行中"
    PLAYER_WINS = "玩家胜利"
    DEALER_WINS = "庄家胜利"
    PUSH = "平局"
    PLAYER_BLACKJACK = "玩家黑杰克"

class BlackjackService:
    """21点游戏服务类"""

    def __init__(self):
        self.active_games: Dict[str, Dict] = {}  # game_id -> game_state

    def _calculate_hand_value(self, hand: List[Card]) -> int:
        """计算手牌点数，智能处理A的点数"""
        value = 0
        aces = 0
        for card in hand:
            value += card.value
            if card.rank == 'A':
                aces += 1
        
        # 如果总点数超过21，且手牌中有A，则将A的点数从11变为1
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
            
        return value

    def start_game(self, user_id: int, guild_id: int, bet_amount: int) -> str:
        """开始一局新的21点游戏"""
        game_id = f"blackjack_{user_id}_{guild_id}"
        deck = Deck()
        
        player_hand = [deck.deal(), deck.deal()]
        dealer_hand = [deck.deal(), deck.deal()]

        player_score = self._calculate_hand_value(player_hand)
        dealer_score = self._calculate_hand_value(dealer_hand)

        status = GameStatus.IN_PROGRESS
        winnings = 0

        # 开局即黑杰克
        if player_score == 21:
            if dealer_score == 21:
                status = GameStatus.PUSH
            else:
                status = GameStatus.PLAYER_BLACKJACK
                winnings = int(bet_amount * 1.5) # 黑杰克赔率1.5
        
        self.active_games[game_id] = {
            "deck": deck,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "player_score": player_score,
            "dealer_score": dealer_score,
            "bet_amount": bet_amount,
            "status": status,
            "winnings": winnings,
        }
        
        return game_id

    def get_game_state(self, game_id: str) -> Optional[Dict]:
        """获取游戏状态"""
        return self.active_games.get(game_id)

    def player_hit(self, game_id: str) -> Optional[Dict]:
        """玩家要牌"""
        game = self.get_game_state(game_id)
        if not game or game["status"] != GameStatus.IN_PROGRESS:
            return None

        game["player_hand"].append(game["deck"].deal())
        game["player_score"] = self._calculate_hand_value(game["player_hand"])

        if game["player_score"] > 21:
            game["status"] = GameStatus.DEALER_WINS
            game["winnings"] = -game["bet_amount"]
        
        return game

    def player_stand(self, game_id: str) -> Optional[Dict]:
        """玩家停牌，轮到庄家行动"""
        game = self.get_game_state(game_id)
        if not game or game["status"] != GameStatus.IN_PROGRESS:
            return None
        
        return self._dealer_turn(game)

    def _dealer_turn(self, game: Dict) -> Dict:
        """庄家行动逻辑"""
        # 庄家在点数小于17时必须叫牌
        while self._calculate_hand_value(game["dealer_hand"]) < 17:
            game["dealer_hand"].append(game["deck"].deal())
        
        game["dealer_score"] = self._calculate_hand_value(game["dealer_hand"])
        player_score = game["player_score"]
        dealer_score = game["dealer_score"]
        bet_amount = game["bet_amount"]

        if dealer_score > 21 or player_score > dealer_score:
            game["status"] = GameStatus.PLAYER_WINS
            game["winnings"] = bet_amount
        elif dealer_score > player_score:
            game["status"] = GameStatus.DEALER_WINS
            game["winnings"] = -bet_amount
        else:
            game["status"] = GameStatus.PUSH
            game["winnings"] = 0
            
        return game

    def end_game(self, game_id: str):
        """结束游戏并清理"""
        if game_id in self.active_games:
            del self.active_games[game_id]

# 全局实例
blackjack_service = BlackjackService()