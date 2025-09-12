import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock
from typing import List, Dict, Any

# 确保 src 目录在 Python 的搜索路径中
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# 模拟 discord 模块，避免真实导入
sys.modules['discord'] = MagicMock()
import discord

# 为 discord.Forbidden 创建一个可捕获的异常模拟
discord.Forbidden = type('Forbidden', (Exception,), {})

# 为 discord.TextChannel 提供一个真实的类作为模拟，以通过 isinstance 检查
discord.TextChannel = type('TextChannel', (object,), {})
# 同样为 MessageType 提供模拟值
discord.MessageType = MagicMock()
discord.MessageType.default = 0
discord.MessageType.reply = 19

from src.chat.services import context_service

class TestContextService(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()

        # --- 模拟依赖 ---
        self.db_manager_mock = AsyncMock()
        self.regex_service_mock = MagicMock()
        self.affection_service_mock = AsyncMock()
        self.world_book_service_mock = MagicMock()
        self.bot_mock = MagicMock()
        self.config_mock = MagicMock()

        # --- 配置模拟对象的返回值 ---
        self.regex_service_mock.clean_user_input.side_effect = lambda x: x # 简单返回原字符串
        self.affection_service_mock.get_affection_status.return_value = {"prompt": "好感度提示"}
        self.world_book_service_mock.get_profile_by_discord_id.return_value = None # 默认无档案
        
        # 模拟 bot 的 user.id
        type(self.bot_mock.user).id = PropertyMock(return_value=12345)
        
        # 模拟 config
        self.config_mock.BRAIN_GIRL_APP_ID = None

        # --- 应用 Patch ---
        self.patcher_db = patch('src.chat.services.context_service.chat_db_manager', self.db_manager_mock)
        self.patcher_regex = patch('src.chat.services.context_service.regex_service', self.regex_service_mock)
        self.patcher_affection = patch('src.chat.services.context_service.affection_service', self.affection_service_mock)
        self.patcher_world_book = patch('src.chat.services.context_service.world_book_service', self.world_book_service_mock)
        self.patcher_config = patch('src.chat.services.context_service.config', self.config_mock)

        self.patcher_db.start()
        self.patcher_regex.start()
        self.patcher_affection.start()
        self.patcher_world_book.start()
        self.patcher_config.start()

        # --- 实例化被测试的服务 ---
        from src.chat.services.context_service import ContextService
        self.context_service = ContextService()
        self.context_service.set_bot_instance(self.bot_mock)

    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_regex.stop()
        self.patcher_affection.stop()
        self.patcher_world_book.stop()
        self.patcher_config.stop()

    def _run_async(self, coro):
        return self.loop.run_until_complete(coro)

    def test_update_user_conversation_history_limit(self):
        """测试用户对话历史是否能正确地保持长度限制。"""
        user_id, guild_id = 1, 101
        
        # 创建一个已经包含10条消息（5轮）的历史记录
        long_history = []
        for i in range(5):
            long_history.append({"role": "user", "parts": [f"msg {i}"]})
            long_history.append({"role": "model", "parts": [f"res {i}"]})
        
        self.db_manager_mock.get_ai_conversation_context.return_value = {"conversation_history": long_history}

        self._run_async(self.context_service.update_user_conversation_history(
            user_id, guild_id, "new message", "new response"
        ))

        # 验证传递给数据库更新函数的是否是最后10条记录
        call_args = self.db_manager_mock.update_ai_conversation_context.call_args
        updated_history = call_args[0][2]
        
        self.assertEqual(len(updated_history), 10)
        self.assertEqual(updated_history[-2]['parts'][0], "new message")
        self.assertEqual(updated_history[-1]['parts'][0], "new response")
        self.assertEqual(updated_history[0]['parts'][0], "msg 1") # 验证第一条旧消息已被移除

    def test_clean_message_content(self):
        """测试消息清理功能。"""
        guild_mock = MagicMock()
        member_mock = MagicMock()
        member_mock.display_name = "TestUser"
        guild_mock.get_member.return_value = member_mock

        raw_content = "你好 <@123456789>，看看这个表情 <:custom_emoji:987654321> 和链接 https://cdn.discordapp.com/..."
        cleaned = self.context_service.clean_message_content(raw_content, guild_mock)

        self.assertEqual(cleaned, "你好 @TestUser，看看这个表情  和链接")
        guild_mock.get_member.assert_called_with(123456789)

    def test_get_formatted_channel_history_merging(self):
        """测试频道历史记录是否能正确合并连续消息。"""
        user_id, guild_id, channel_id = 1, 101, 1001
        
        # 模拟 Discord 消息对象
        def create_mock_message(author_id, content, msg_id):
            msg = MagicMock()
            msg.author.id = author_id
            msg.author.display_name = f"User_{author_id}"
            msg.content = content
            msg.id = msg_id
            msg.type = discord.MessageType.default
            msg.attachments = []
            msg.reference = None
            msg.guild = MagicMock()
            return msg

        # 模拟历史消息：用户1，用户2，机器人，用户1
        mock_history = [
            create_mock_message(1, "Hello", 1),
            create_mock_message(2, "Hi there", 2),
            create_mock_message(self.bot_mock.user.id, "I am a bot", 3),
            create_mock_message(1, "How are you?", 4),
        ]

        # 模拟 channel.history
        async def mock_history_iterator(*args, **kwargs):
            for msg in reversed(mock_history):
                yield msg
        
        # 使用 spec 来确保 mock 对象能通过 isinstance(channel, discord.TextChannel) 检查
        channel_mock = MagicMock(spec=discord.TextChannel)
        # 明确地为 mock 对象添加 history 属性，并将其设置为一个可以返回异步迭代器的 mock
        channel_mock.history = MagicMock()
        channel_mock.guild = MagicMock()
        channel_mock.guild.id = guild_id
        channel_mock.history.return_value = mock_history_iterator()
        self.bot_mock.get_channel.return_value = channel_mock
        
        # 模拟数据库无锚点
        self.db_manager_mock.get_channel_memory_anchor.return_value = None

        result = self._run_async(self.context_service.get_formatted_channel_history(channel_id, user_id, guild_id))

        # 预期结果：
        # 1. 用户1和用户2的消息合并为一个 'user' role
        # 2. 机器人的消息为一个 'model' role
        # 3. 用户1的最后一条消息为一个 'user' role
        # 4. 最后注入一个 'model' role 的上下文提示
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]['role'], 'user')
        self.assertIn("User_1: Hello", result[0]['parts'][0])
        self.assertIn("User_2: Hi there", result[0]['parts'][0])
        
        self.assertEqual(result[1]['role'], 'model')
        self.assertIn("User_12345: I am a bot", result[1]['parts'][0])

        self.assertEqual(result[2]['role'], 'user')
        self.assertIn("User_1: How are you?", result[2]['parts'][0])

        self.assertEqual(result[3]['role'], 'model')
        self.assertIn("好感度提示", result[3]['parts'][0])

    def test_clear_user_context(self):
        """测试清除用户上下文功能。"""
        user_id, guild_id = 1, 101
        self._run_async(self.context_service.clear_user_context(user_id, guild_id))
        self.db_manager_mock.clear_ai_conversation_context.assert_called_once_with(user_id, guild_id)

    def test_get_channel_conversation_history_simple(self):
        """测试获取频道原始对话历史。"""
        channel_id = 1001

        def create_mock_message(author_id, content, msg_id):
            msg = MagicMock()
            msg.author.id = author_id
            msg.author.display_name = f"User_{author_id}"
            msg.content = content
            msg.id = msg_id
            msg.type = discord.MessageType.default
            msg.guild = MagicMock()
            return msg

        mock_history = [
            create_mock_message(1, "Hello", 1),
            create_mock_message(2, "Hi there", 2),
        ]

        async def mock_history_iterator(*args, **kwargs):
            for msg in reversed(mock_history):
                yield msg
        
        channel_mock = MagicMock(spec=discord.TextChannel)
        channel_mock.history.return_value = mock_history_iterator()
        self.bot_mock.get_channel.return_value = channel_mock

        result = self._run_async(self.context_service.get_channel_conversation_history(channel_id))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['parts'][0], "User_1: Hello")
        self.assertEqual(result[1]['parts'][0], "User_2: Hi there")

    def test_get_formatted_channel_history_with_anchor(self):
        """测试使用记忆锚点获取频道历史记录。"""
        user_id, guild_id, channel_id = 1, 101, 1001
        anchor_id = 2 # Anchor after the second message

        def create_mock_message(author_id, content, msg_id):
            msg = MagicMock()
            msg.author.id = author_id
            msg.author.display_name = f"User_{author_id}"
            msg.content = content
            msg.id = msg_id
            msg.type = discord.MessageType.default
            msg.attachments = []
            msg.reference = None
            msg.guild = MagicMock()
            return msg

        mock_history = [
            create_mock_message(1, "Old message", 1),
            create_mock_message(2, "Anchor message", anchor_id),
            create_mock_message(self.bot_mock.user.id, "Bot reply", 3),
            create_mock_message(1, "New message", 4),
        ]

        # When 'after' is used, discord.py returns messages from oldest to newest
        async def mock_history_iterator_after(*args, **kwargs):
            # The history call will be channel.history(limit=fetch_limit, after=after_message)
            # It should return messages with ID > anchor_id
            for msg in mock_history:
                if msg.id > anchor_id:
                    yield msg
        
        channel_mock = MagicMock(spec=discord.TextChannel)
        channel_mock.history.return_value = mock_history_iterator_after()
        channel_mock.guild = MagicMock()
        channel_mock.guild.id = guild_id
        self.bot_mock.get_channel.return_value = channel_mock
        
        # Simulate database has an anchor
        self.db_manager_mock.get_channel_memory_anchor.return_value = anchor_id

        result = self._run_async(self.context_service.get_formatted_channel_history(channel_id, user_id, guild_id))

        # 预期结果:
        # 1. 机器人的消息 (model)
        # 2. 用户的消息 (user)
        # 3. 最后注入一个 'model' role 的上下文提示
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['role'], 'model')
        self.assertIn("User_12345: Bot reply", result[0]['parts'][0])
        self.assertEqual(result[1]['role'], 'user')
        self.assertIn("User_1: New message", result[1]['parts'][0])
        self.assertEqual(result[2]['role'], 'model')
        self.assertIn("好感度提示", result[2]['parts'][0])

if __name__ == '__main__':
    unittest.main()