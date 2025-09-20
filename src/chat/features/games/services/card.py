# -*- coding: utf-8 -*-

import random
from typing import List, Dict

# 定义花色和点数的Unicode字符表示，增加视觉效果
SUITS: Dict[str, str] = {
    "Hearts": "♥️",
    "Diamonds": "♦️",
    "Clubs": "♣️",
    "Spades": "♠️",
}

RANKS: Dict[str, int] = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, 
    "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10
}

class Card:
    """代表一张扑克牌"""
    def __init__(self, suit: str, rank: str):
        if suit not in SUITS:
            raise ValueError(f"Invalid suit: {suit}")
        if rank not in RANKS:
            raise ValueError(f"Invalid rank: {rank}")
        
        self.suit: str = suit
        self.rank: str = rank
        self.value: int = RANKS[rank]

    def __str__(self) -> str:
        return f"{SUITS[self.suit]}{self.rank}"

    def __repr__(self) -> str:
        return f"Card('{self.suit}', '{self.rank}')"

class Deck:
    """代表一副或多副扑克牌"""
    def __init__(self, num_decks: int = 1):
        if num_decks < 1:
            raise ValueError("Number of decks must be at least 1.")
        
        self.cards: List[Card] = self._generate_decks(num_decks)
        self.shuffle()

    def _generate_decks(self, num_decks: int) -> List[Card]:
        """生成指定数量的牌组"""
        cards = []
        for _ in range(num_decks):
            for suit in SUITS:
                for rank in RANKS:
                    cards.append(Card(suit, rank))
        return cards

    def shuffle(self) -> None:
        """洗牌"""
        random.shuffle(self.cards)

    def deal(self) -> Card:
        """发一张牌"""
        if not self.cards:
            raise ValueError("Deck is empty.")
        return self.cards.pop()

    def __len__(self) -> int:
        return len(self.cards)
