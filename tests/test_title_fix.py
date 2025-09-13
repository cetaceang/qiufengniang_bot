#!/usr/bin/env python3
"""
测试脚本：验证用户档案标题修复功能
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath('.'))

from src.chat.features.personal_memory.services.personal_memory_service import PersonalMemoryService

async def test_title_fix():
    """测试用户档案标题更新功能"""
    service = PersonalMemoryService()
    
    # 测试数据
    test_user_id = 999999999  # 使用一个不存在的测试用户ID
    profile_data = {
        'name': '测试用户',
        'personality': '测试性格',
        'background': '测试背景',
        'preferences': '测试偏好'
    }
    
    print("=== 测试用户档案标题修复 ===")
    print(f"测试用户ID: {test_user_id}")
    print(f"测试姓名: {profile_data['name']}")
    
    try:
        # 第一次保存（创建新档案）
        print("\n1. 第一次保存 - 创建新档案")
        await service.save_user_profile(test_user_id, profile_data)
        print("✓ 新档案创建成功")
        
        # 修改姓名
        profile_data['name'] = '更新后的用户'
        print(f"\n2. 更新姓名为: {profile_data['name']}")
        
        # 第二次保存（更新现有档案）
        await service.save_user_profile(test_user_id, profile_data)
        print("✓ 档案更新成功")
        
        # 验证数据库中的标题是否正确更新
        from src.chat.features.world_book.services.world_book_service import world_book_service
        
        result = world_book_service.get_profile_by_discord_id(str(test_user_id))
        if result:
            print(f"\n3. 验证数据库中的标题:")
            print(f"   数据库标题: {result.get('title')}")
            print(f"   期望标题: 用户档案 - {profile_data['name']}")
            
            expected_title = f"用户档案 - {profile_data['name']}"
            if result.get('title') == expected_title:
                print("✓ 标题更新验证成功！")
                return True
            else:
                print("✗ 标题更新验证失败！")
                return False
        else:
            print("✗ 无法从数据库获取用户档案")
            return False
            
    except Exception as e:
        print(f"✗ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_title_fix())
    if success:
        print("\n🎉 所有测试通过！标题修复功能正常工作。")
        sys.exit(0)
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)