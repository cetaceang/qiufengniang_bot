#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抽鬼牌游戏测试脚本
用于验证新的游戏逻辑是否正确
"""

import sys
import os
import unittest
import random
from unittest.mock import MagicMock, patch

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from games.services.ghost_card_service import GhostCardService, AIStrategy

class TestGhostCardService(unittest.TestCase):
    """测试抽鬼牌游戏服务"""

    def setUp(self):
        """在每个测试前执行"""
        self.service = GhostCardService()
        print(f"\n{'='*10} Running test: {self.id()} {'='*10}")

    def test_01_generate_deck(self):
        """1. 测试生成牌组"""
        print("🧪 1. 测试生成牌组...")
        deck = self.service.generate_deck()
        self.assertEqual(len(deck), 17)  # 8对牌 + 1张鬼牌
        self.assertIn("👑", deck)
        self.assertEqual(deck.count("👑"), 1)
        print(f"牌组大小: {len(deck)} 张牌, 包含鬼牌: {'👑' in deck}")
        print("✅ 测试通过！")

    def test_02_determine_ai_strategy(self):
        """2. 测试AI策略分布"""
        print("🧪 2. 测试AI策略分布...")
        strategy_counts = {strategy: 0 for strategy in AIStrategy}
        total_runs = 10000
        for _ in range(total_runs):
            strategy = self.service.determine_ai_strategy()
            strategy_counts[strategy] += 1
        
        for strategy, count in strategy_counts.items():
            percentage = (count / total_runs) * 100
            print(f"{strategy.value}: {count}次 ({percentage:.2f}%)")
        
        # 检查概率是否在合理范围内
        self.assertLess(abs(strategy_counts[AIStrategy.SUPER] / total_runs - 0.01), 0.005)
        print("✅ 测试通过！")

    def test_03_match_and_discard(self):
        """3. 测试配对和弃牌逻辑"""
        print("🧪 3. 测试配对和弃牌逻辑...")
        hand1 = ["A", "A", "2", "3", "👑"]
        result1 = self.service._match_and_discard(hand1)
        self.assertCountEqual(result1, ["2", "3", "👑"])
        print(f"手牌 {hand1} -> {result1}")

        hand2 = ["A", "A", "2", "2"]
        result2 = self.service._match_and_discard(hand2)
        self.assertCountEqual(result2, [])
        print(f"手牌 {hand2} -> {result2}")

        hand3 = ["A", "2", "3", "👑"]
        result3 = self.service._match_and_discard(hand3)
        self.assertCountEqual(result3, ["A", "2", "3", "👑"])
        print(f"手牌 {hand3} -> {result3}")
        print("✅ 测试通过！")

    def test_04_full_game_flow_player_wins(self):
        """4. 测试完整游戏流程 - 玩家获胜"""
        print("🧪 4. 测试完整游戏流程 - 玩家获胜...")
        user_id, guild_id, bet_amount = 123, 456, 100
        strategy = AIStrategy.LOW
        
        game_id = self.service.start_new_game(user_id, guild_id, bet_amount, strategy)
        game_state = self.service.get_game_state(game_id)
        
        print(f"游戏开始! ID: {game_id}, AI策略: {strategy.value}")
        print(f"玩家手牌: {game_state['player_hand']}")
        print(f"AI手牌: {game_state['ai_hand']}")
        print(f"先手: {game_state['current_turn']}")

        # 强制设置手牌以确保测试的可预测性
        game_state['player_hand'] = ['A', '2']
        game_state['ai_hand'] = ['A', '👑']
        game_state['current_turn'] = 'player'
        
        print("\n--- 强制设定手牌 ---")
        print(f"玩家手牌: {game_state['player_hand']}")
        print(f"AI手牌: {game_state['ai_hand']}")

        # 玩家回合
        print("\n--- 玩家回合 ---")
        self.assertEqual(game_state['current_turn'], 'player')
        # 玩家抽AI的 'A'
        success, msg, _, _ = self.service.player_draw_card(game_id, 0)
        self.assertTrue(success)
        print(f"玩家抽牌结果: {msg}")
        # After drawing 'A', player has ['A', 'A', '2'], after discard, player has ['2']
        game_state['player_hand'] = self.service._match_and_discard(game_state['player_hand'])
        print(f"玩家手牌 (抽后): {game_state['player_hand']}")
        self.assertCountEqual(game_state['player_hand'], ['2'])

        # AI回合
        print("\n--- AI 回合 ---")
        self.assertEqual(game_state['current_turn'], 'ai')
        # AI 抽玩家的 '2'
        success, msg, _, _ = self.service.ai_draw_card(game_id)
        self.assertTrue(success)
        print(f"AI抽牌结果: {msg}")
        # After drawing '2', AI has ['👑', '2'], after discard, AI has ['👑', '2']
        print(f"AI手牌 (抽后): {game_state['ai_hand']}")
        self.assertCountEqual(game_state['ai_hand'], ['2', '👑'])
        
        # 游戏结束检查
        self.assertTrue(game_state['game_over'])
        self.assertEqual(game_state['winner'], 'player')
        print(f"\n游戏结束! 胜利者: {game_state['winner']}")
        print("✅ 测试通过！")

    @patch('src.games.services.ghost_card_service.GhostCardService.ai_make_decision')
    def test_05_full_game_flow_ai_wins(self, mock_ai_decision):
        """5. 测试完整游戏流程 - AI获胜"""
        print("🧪 5. 测试完整游戏流程 - AI获胜...")
        
        # 模拟AI决策，确保它总是选择第一张牌
        mock_ai_decision.return_value = 0

        user_id, guild_id, bet_amount = 789, 101, 50
        # 策略设为HIGH，但由于mock，实际决策是固定的
        strategy = AIStrategy.HIGH
        
        game_id = self.service.start_new_game(user_id, guild_id, bet_amount, strategy)
        game_state = self.service.get_game_state(game_id)

        # 强制设置手牌
        game_state['player_hand'] = ['A', '👑']
        game_state['ai_hand'] = ['A', '2']
        game_state['current_turn'] = 'ai' # 强制AI先手
        
        print("--- 强制设定手牌 ---")
        print(f"玩家手牌: {game_state['player_hand']}")
        print(f"AI手牌: {game_state['ai_hand']}")

        # AI 回合
        print("\n--- AI 回合 ---")
        # AI 抽玩家的 'A', AI手牌配对后剩下['2'], 玩家手牌剩下['👑']
        success, msg, _, _ = self.service.ai_draw_card(game_id)
        self.assertTrue(success)
        print(f"AI抽牌结果: {msg}")
        print(f"AI手牌 (抽后): {game_state['ai_hand']}")
        self.assertCountEqual(game_state['player_hand'], ['👑'])
        self.assertCountEqual(game_state['ai_hand'], ['2'])

        # 玩家回合
        print("\n--- 玩家回合 ---")
        # 玩家抽AI的 '2', AI手牌为空，AI获胜
        success, msg, _, _ = self.service.player_draw_card(game_id, 0)
        self.assertTrue(success)
        print(f"玩家抽牌结果: {msg}")
        print(f"玩家手牌 (抽后): {game_state['player_hand']}")
        
        # 游戏结束检查
        self.assertTrue(game_state['game_over'])
        self.assertEqual(game_state['winner'], 'ai')
        # AI获胜，手牌应为空
        self.assertCountEqual(game_state['ai_hand'], [])
        self.assertIn("你输了", msg)
        print(f"\n游戏结束! 胜利者: {game_state['winner']}")
        print("✅ 测试通过！")

    def test_06_win_rate_simulation(self):
        """6. 测试不同策略下的胜率分布"""
        print("🧪 6. 测试不同策略下的胜率分布...")
        simulations = 1000  # 每种策略模拟1000次
        results = {}

        for strategy in AIStrategy:
            wins = {"player": 0, "ai": 0}
            for i in range(simulations):
                user_id = f"sim_{strategy.name}_{i}"
                game_id = self.service.start_new_game(user_id, 1, 10, strategy)
                
                game_over = False
                turn_limit = 50 # 防止无限循环
                turn_count = 0

                while not game_over and turn_count < turn_limit:
                    game_state = self.service.get_game_state(game_id)
                    if not game_state: break

                    current_turn = game_state['current_turn']
                    
                    if current_turn == 'player':
                        if not game_state['ai_hand']:
                            game_state['winner'] = 'player'
                            game_state['game_over'] = True
                        else:
                            # 玩家随机抽一张牌
                            card_index = random.randint(0, len(game_state['ai_hand']) - 1)
                            self.service.player_draw_card(game_id, card_index)
                    else: # AI turn
                        if not game_state['player_hand']:
                            game_state['winner'] = 'ai'
                            game_state['game_over'] = True
                        else:
                            self.service.ai_draw_card(game_id)
                    
                    game_over = game_state['game_over']
                    turn_count += 1

                if game_state and game_state['winner']:
                    wins[game_state['winner']] += 1
                
                self.service.end_game(game_id)

            results[strategy.name] = wins
        
        print("\n--- 胜率模拟结果 ---")
        for strategy_name, wins in results.items():
            player_wins = wins['player']
            ai_wins = wins['ai']
            total = player_wins + ai_wins
            player_win_rate = (player_wins / total) * 100 if total > 0 else 0
            print(f"策略: {strategy_name}, 玩家胜率: {player_win_rate:.2f}% ({player_wins}/{total})")
        
        print("✅ 测试通过！")

    def test_07_overall_win_rate_simulation(self):
        """7. 测试随机策略下的综合胜率"""
        print("🧪 7. 测试随机策略下的综合胜率...")
        simulations = 10000
        wins = {"player": 0, "ai": 0}

        for i in range(simulations):
            # 每局游戏都随机决定AI策略
            strategy = self.service.determine_ai_strategy()
            user_id = f"overall_sim_{i}"
            game_id = self.service.start_new_game(user_id, 1, 10, strategy)
            
            game_over = False
            turn_limit = 50
            turn_count = 0

            while not game_over and turn_count < turn_limit:
                game_state = self.service.get_game_state(game_id)
                if not game_state: break

                current_turn = game_state['current_turn']
                
                if current_turn == 'player':
                    if not game_state['ai_hand']:
                        game_state['winner'] = 'player'
                        game_state['game_over'] = True
                    else:
                        card_index = random.randint(0, len(game_state['ai_hand']) - 1)
                        self.service.player_draw_card(game_id, card_index)
                else: # AI turn
                    if not game_state['player_hand']:
                        game_state['winner'] = 'ai'
                        game_state['game_over'] = True
                    else:
                        self.service.ai_draw_card(game_id)
                
                game_over = game_state['game_over']
                turn_count += 1

            if game_state and game_state['winner']:
                wins[game_state['winner']] += 1
            
            self.service.end_game(game_id)

        print("\n--- 综合胜率模拟结果 ---")
        player_wins = wins['player']
        ai_wins = wins['ai']
        total = player_wins + ai_wins
        player_win_rate = (player_wins / total) * 100 if total > 0 else 0
        print(f"总计: {total} 局, 玩家胜率: {player_win_rate:.2f}% ({player_wins}/{total})")
        print("✅ 测试通过！")

if __name__ == "__main__":
    unittest.main()