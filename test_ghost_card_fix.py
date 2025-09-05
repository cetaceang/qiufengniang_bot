#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试抽鬼牌欺骗逻辑修复
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from games.services.ghost_card_service import GhostCardService, AIStrategy

def test_deception_logic():
    """测试欺骗逻辑修复"""
    service = GhostCardService()
    
    print("测试抽鬼牌欺骗逻辑修复")
    print("=" * 50)
    
    # 测试场景1: AI手上有鬼牌时，可以欺骗
    print("场景1: AI手上有鬼牌")
    ai_has_ghost = True
    is_ghost = False  # 玩家选中的是普通牌
    
    for strategy in [AIStrategy.LOW, AIStrategy.MEDIUM, AIStrategy.HIGH, AIStrategy.SUPER]:
        print(f"\n策略: {strategy.value}")
        for i in range(3):  # 测试3次
            text, image_url, deception_type = service._get_bot_reaction(
                "selected", is_ghost, strategy, ai_has_ghost
            )
            print(f"  测试 {i+1}: 欺骗类型={deception_type}, 反应='{text}'")
    
    # 测试场景2: AI手上没有鬼牌时，不应该欺骗
    print("\n场景2: AI手上没有鬼牌")
    ai_has_ghost = False
    is_ghost = False  # 玩家选中的是普通牌
    
    for strategy in [AIStrategy.LOW, AIStrategy.MEDIUM, AIStrategy.HIGH, AIStrategy.SUPER]:
        print(f"\n策略: {strategy.value}")
        for i in range(3):  # 测试3次
            text, image_url, deception_type = service._get_bot_reaction(
                "selected", is_ghost, strategy, ai_has_ghost
            )
            print(f"  测试 {i+1}: 欺骗类型={deception_type}, 反应='{text}'")
            # 验证：当AI没有鬼牌时，不应该有欺骗
            if deception_type is not None:
                print(f"  ❌ 错误: AI没有鬼牌时不应该欺骗!")
                return False
    
    print("\n✅ 测试通过: AI没有鬼牌时不会进行欺骗")
    return True

if __name__ == "__main__":
    success = test_deception_logic()
    if success:
        print("\n🎉 所有测试通过！修复成功！")
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)