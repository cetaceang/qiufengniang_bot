#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多API密钥测试脚本
用于验证Gemini服务的多密钥轮询功能
"""

import sys
import os

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from services.gemini_service import GeminiService

def test_multi_api_keys():
    """测试多API密钥功能"""
    print("🔑 测试多API密钥功能...")
    
    # 模拟多个API密钥
    os.environ['GEMINI_API_KEY'] = "key1,key2,key3"
    
    service = GeminiService()
    
    print(f"检测到的API密钥数量: {len(service.api_keys)}")
    print(f"可用的模型数量: {len(service.models)}")
    print(f"服务可用性: {service.is_available()}")
    
    # 测试轮询功能
    print("\n🔁 测试轮询功能...")
    for i in range(10):
        model = service.get_next_model()
        if model:
            print(f"请求 #{i+1}: 使用密钥索引 {service.current_key_index}")
        else:
            print(f"请求 #{i+1}: 无可用模型")
    
    print("\n✅ 多API密钥测试完成！")

if __name__ == "__main__":
    test_multi_api_keys()