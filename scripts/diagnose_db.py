# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import json

# 将 src 目录添加到 Python 路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from utils.database import db_manager
from config import GUILD_ID

async def main():
    """
    主函数，用于连接数据库并打印出所有的 channel_messages 数据。
    """
    if not GUILD_ID:
        print("错误：请在 .env 文件中设置 GUILD_ID")
        return

    guild_id = int(GUILD_ID)

    print(f"正在从数据库中为服务器 {guild_id} 读取所有频道消息配置...")
    
    try:
        all_channel_messages = await db_manager.get_all_channel_messages(guild_id)
        
        if not all_channel_messages:
            print("数据库中没有找到任何频道消息配置。")
            return
            
        print(f"✅ 查询成功，找到 {len(all_channel_messages)} 条配置记录。\n")
        
        for message_config in all_channel_messages:
            print("-" * 40)
            print(f"配置信息 (Channel ID: {message_config.get('channel_id')})")
            print("-" * 40)
            
            # 使用 json.dumps 格式化输出，确保中文和缩进正确
            formatted_config = json.dumps(message_config, indent=2, ensure_ascii=False)
            print(formatted_config)
            print("\n")

    except Exception as e:
        print(f"❌ 从数据库读取数据时发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
