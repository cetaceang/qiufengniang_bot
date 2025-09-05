# -*- coding: utf-8 -*-

import os
import logging
from typing import Optional, Dict, List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime, timezone, timedelta
import re
import random

import requests
from PIL import Image
import io

# 导入新库
from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions

# 导入数据库管理器和提示词配置
from ..utils.database import db_manager
from config.prompts import SYSTEM_PROMPT
from config.emoji_config import EMOJI_MAPPINGS
from src import config
from ..affection.service.affection_service import affection_service
from .context_service import context_service
from .regex_service import regex_service
from ..world_book.services.world_book_service import world_book_service
 
log = logging.getLogger(__name__)

class GeminiService:
    """Gemini AI 服务类，使用数据库存储用户对话上下文"""
    
    def __init__(self):
        # 支持多个API密钥轮询，用逗号分隔
        api_keys_str = os.getenv("GEMINI_API_KEYS", "")
        # 支持多行和逗号分隔的密钥
        self.api_keys = [key.strip() for line in api_keys_str.splitlines() for key in line.split(',') if key.strip()]
        self.current_key_index = 0
        self.model_name = config.GEMINI_MODEL
        self.clients = {}  # 存储每个API密钥对应的客户端
        self.executor = ThreadPoolExecutor(max_workers=10)  # 增加工作线程数
        self.user_request_timestamps: Dict[int, List[datetime]] = {}  # 用户请求时间戳，用于冷却
        self.initialize_clients()
    
    def initialize_clients(self):
        """初始化所有Gemini客户端（支持多个API密钥）"""
        if not self.api_keys:
            log.warning("GEMINI_API_KEYS 未设置，AI功能将不可用")
            return
        
        for i, api_key in enumerate(self.api_keys):
            try:
                # 为每个API密钥创建独立的客户端
                client = genai.Client(api_key=api_key)
                self.clients[api_key] = client
                log.info(f"Gemini客户端 (密钥 #{i+1}) 初始化成功")
            except Exception as e:
                log.error(f"初始化Gemini客户端 (密钥 #{i+1}) 失败: {e}")
        
        if not self.clients:
            log.error("所有API密钥初始化失败，AI功能将不可用")
    
    async def get_user_conversation_history(self, user_id: int, guild_id: int) -> List[Dict]:
        """从数据库获取用户的对话历史"""
        context = await db_manager.get_ai_conversation_context(user_id, guild_id)
        if context and context.get('conversation_history'):
            return context['conversation_history']
        return []
    
    
    def get_next_client(self):
        """获取下一个可用的客户端（轮询模式）"""
        if not self.clients:
            return None
        
        # 轮询选择下一个API密钥
        api_keys = list(self.clients.keys())
        selected_key = api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(api_keys)
        
        return self.clients[selected_key]
    
    async def _check_and_update_cooldown(self, user_id: int, cooldown_type: str = "default") -> bool:
        """
        检查并更新用户的冷却状态。
        Args:
            user_id: 用户ID
            cooldown_type: 冷却类型，"default" 为每分钟2次，"coffee" 为每分钟5次。
        Returns:
            bool: 如果用户在冷却期内，返回 False；否则返回 True。
        """
        now = datetime.now(timezone.utc)
        
        # 根据冷却类型设置限制
        if cooldown_type == "coffee":
            rate_limit = 5  # 每分钟5次
        else: # default
            rate_limit = 2  # 每分钟2次

        # 清理旧的时间戳
        self.user_request_timestamps[user_id] = [
            ts for ts in self.user_request_timestamps.get(user_id, [])
            if now - ts < timedelta(minutes=1)
        ]

        if len(self.user_request_timestamps.get(user_id, [])) >= rate_limit:
            log.warning(f"用户 {user_id} 触发了 {cooldown_type} 冷却限制。")
            return False
        
        self.user_request_timestamps.setdefault(user_id, []).append(now)
        return True

    async def is_user_on_cooldown(self, user_id: int, cooldown_type: str = "default") -> bool:
        """
        仅检查用户是否处于冷却状态，不更新时间戳。
        Returns:
            bool: 如果用户在冷却期内，返回 True；否则返回 False。
        """
        now = datetime.now(timezone.utc)
        
        if cooldown_type == "coffee":
            rate_limit = 5
        else: # default
            rate_limit = 2

        # 清理旧的时间戳
        timestamps = [
            ts for ts in self.user_request_timestamps.get(user_id, [])
            if now - ts < timedelta(minutes=1)
        ]
        self.user_request_timestamps[user_id] = timestamps

        if len(timestamps) >= rate_limit:
            return True
        
        return False

    async def generate_response(self, user_id: int, guild_id: int, message: str,
                                images: Optional[List[Dict]] = None, user_name: str = "用户",
                                channel_context: Optional[List[Dict]] = None,
                                world_book_entries: Optional[List[Dict]] = None,
                                cooldown_type: str = "default") -> str:
        """
        生成AI回复（已重构）。
        此版本使用结构化的多轮对话历史，以实现更准确的上下文理解。

        Args:
            user_id: 用户ID
            guild_id: 服务器ID
            message: 用户当前消息的纯文本
            images: 图像数据列表
            user_name: 当前交互的用户名
            channel_context: 从 context_service 获取的结构化频道历史

        Returns:
            str: AI生成的回复
        """
        if not self.clients:
            return "抱歉，类脑娘暂时休息啦，请稍后再试～ "

        # 检查冷却状态
        if not await self._check_and_update_cooldown(user_id, cooldown_type):
            return None

        try:
            beijing_tz = timezone(timedelta(hours=8))
            current_beijing_time = datetime.now(beijing_tz).strftime('%Y年%m月%d日 %H:%M')
            
            # --- 重构：处理世界书条目列表 ---
            world_book_formatted_content = ""
            subject_name = "对方" # 默认值
            if world_book_entries:
                # 将所有世界书条目的内容合并
                all_contents = []
                for entry in world_book_entries:
                    if 'content' in entry:
                        all_contents.append(entry['content'])
                
                if all_contents:
                    world_book_formatted_content = "<world_book_context>\n" + "\n---\n".join(all_contents) + "\n</world_book_context>"
                
                # 使用优先级最高的条目ID作为主题名称
                subject_name = world_book_entries[0].get('id', '多个主题') if world_book_entries else '多个主题'

            # --- 结束 ---

            # 获取用户好感度信息
            affection_status = await affection_service.get_affection_status(user_id, guild_id)
            affection_level_prompt = affection_status.get("prompt", "") # 获取好感度等级对应的提示词

            dynamic_system_prompt = SYSTEM_PROMPT.format(
                current_time=current_beijing_time,
                user_name=user_name,
                world_book_content=world_book_formatted_content,
                affection_level_prompt=affection_level_prompt, # 注入好感度等级提示词
                subject_name=subject_name
            )

            final_conversation = [{"role": "user", "parts": [dynamic_system_prompt]}, {"role": "model", "parts": ["好的，我明白了。"]}]
            
            # 1. 合并频道上下文
            if channel_context:
                final_conversation.extend(channel_context)
                log.debug(f"已合并频道上下文，长度为: {len(channel_context)}")

            # --- "严格遵守官方示例" 的图片处理逻辑 ---
            current_user_parts = [] # 这将是一个简单的列表 [str, Image, Image, ...]

            # 1. 添加文本部分
            text_part_content = ""
            if message:
                text_part_content = f'{user_name}: {message}'
            elif images:
                text_part_content = f'{user_name}: (图片消息)'
            
            if text_part_content:
                current_user_parts.append(text_part_content)

            # 2. 处理并添加所有图片为 PIL.Image 对象
            if images:
                log.debug(f"收到 {len(images)} 个图片附件，将使用 Pillow 直接处理。")
                for i, img_data in enumerate(images):
                    image_bytes = None
                    source_type = ""

                    # 获取图片字节
                    if 'data' in img_data: # 本地上传
                        image_bytes = img_data['data']
                        source_type = "本地"
                    elif 'url' in img_data: # 网络图片
                        try:
                            log.debug(f"正在下载网络图片: {img_data['url']}")
                            response = requests.get(img_data['url'])
                            response.raise_for_status()
                            image_bytes = response.content
                            source_type = "网络"
                        except requests.exceptions.RequestException as e:
                            log.error(f"下载网络图片 {img_data['url']} 时出错: {e}")
                            continue # 跳过这张失败的图片

                    # 将字节转换为 PIL.Image 对象
                    if image_bytes:
                        try:
                            pil_image = Image.open(io.BytesIO(image_bytes))
                            current_user_parts.append(pil_image) # 直接添加原始 PIL.Image 对象
                            log.debug(f"{source_type}图片附件 {i+1} 成功转换为 PIL.Image 对象。")
                        except Exception as e:
                            log.error(f"Pillow 无法打开{source_type}图片附件 {i+1}。错误: {e}。将跳过此图片。")
                    else:
                        log.warning(f"图片附件 {i+1} 数据无效或下载失败。")

            # 3. 只有当存在有效内容时，才追加。
            #    同时，检查并处理连续出现'user'角色的情况。
            if current_user_parts:
                # 如果最后一条消息也是'user'，则将当前消息合并进去，以避免API错误
                if final_conversation and final_conversation[-1].get("role") == "user":
                    final_conversation[-1]["parts"].extend(current_user_parts)
                else:
                    # 否则，作为一个新的'user'轮次追加
                    final_conversation.append({"role": "user", "parts": current_user_parts})

            # 循环尝试所有API密钥
            for i in range(len(self.clients)):
                client = self.get_next_client()
                if not client:
                    continue

                log.info(f"正在使用 API 密钥 #{self.current_key_index} 为用户 {user_id} 生成回复...")
                
                try:
                    try:
                        # 自定义序列化函数，以解决 Part 和 Image 对象无法被 JSON 序列化的问题
                        def serialize_parts(obj):
                            if isinstance(obj, types.Part):
                                if obj.text:
                                    return {"type": "text", "content": obj.text}
                                elif obj.inline_data:
                                    return {"type": "image", "mime_type": obj.inline_data.mime_type, "data_size": len(obj.inline_data.data)}
                            elif isinstance(obj, Image.Image):
                                return f"<PIL.Image object: mode={obj.mode}, size={obj.size}>"
                            # 对于其他无法序列化的类型，返回其字符串表示形式
                            try:
                                # 尝试默认转换
                                return json.JSONEncoder().default(obj)
                            except TypeError:
                                return str(obj)

                        log.info(f"发送给 Gemini 的请求体: \n{json.dumps(final_conversation, indent=2, ensure_ascii=False, default=serialize_parts)}")
                    except Exception as e:
                        log.error(f"序列化请求体用于日志记录时失败: {e}")

                    loop = asyncio.get_event_loop()
                    # 准备 generate_content 的参数
                    gen_config = types.GenerateContentConfig(
                        temperature=1.1,
                        top_p=0.95,
                        top_k=60,
                        max_output_tokens=400,
                    )
                    
                    # 为 Flash 模型关闭思考功能
                    if 'flash' in self.model_name.lower():
                        gen_config.thinking_config = types.ThinkingConfig(thinking_budget=0)
                        log.info("检测到 Flash 模型，已通过正确的 thinking_config 禁用思考功能。")

                    # --- 严格按照官方示例组合 contents ---
                    # 历史记录部分需要被严格构造成 Content 对象
                    # 当前用户消息部分则是一个包含 [str, Image] 的简单列表
                    processed_contents = []
                    for conversation_turn in final_conversation:
                        role = conversation_turn.get("role")
                        parts_data = conversation_turn.get("parts", [])

                        if not (role and parts_data):
                            continue

                        # 【修复关键】创建一个新的列表，用于存放被显式转换后的 Part 对象
                        processed_parts = []
                        for part_item in parts_data:
                            if isinstance(part_item, str):
                                # 对所有字符串，都明确地用 types.Part 封装
                                processed_parts.append(types.Part(text=part_item))
                            elif isinstance(part_item, Image.Image):
                                # 【修复】将 PIL.Image 对象转换为 Base64 编码的字符串
                                buffered = io.BytesIO()
                                part_item.save(buffered, format="PNG") # 或者 JPEG
                                img_bytes = buffered.getvalue()
                                
                                # 创建一个符合 SDK 要求的 Part 对象
                                # 注意：这里我们不直接进行 base64 编码，因为 SDK 的 Part 结构会处理
                                # 我们需要提供原始字节和 MIME 类型
                                processed_parts.append(types.Part(
                                    inline_data=types.Blob(
                                        mime_type='image/png', # 或 'image/jpeg'
                                        data=img_bytes
                                    )
                                ))

                        # 确保有有效的部分再创建 Content 对象
                        if processed_parts:
                            processed_contents.append(types.Content(role=role, parts=processed_parts))

                    response = await loop.run_in_executor(
                        self.executor,
                        lambda: client.models.generate_content(
                            model=self.model_name,
                            contents=processed_contents, # 现在包含混合结构
                            config=gen_config
                        )
                    )
                    
                    if response.parts:
                        raw_ai_response = response.text.strip()
                        
                        await context_service.update_user_conversation_history(
                            user_id, guild_id,
                            message if message else "",
                            raw_ai_response
                        )
                        
                        # 1. 强化对AI模仿的回复前缀的清理
                        #    - 支持全角/半角括号
                        #    - 支持多种空格形式
                        reply_prefix_pattern = re.compile(r'^\s*([\[［]【回复|回复}\s*@.*?[\)）\]］])\s*', re.IGNORECASE)
                        formatted_ai_response = reply_prefix_pattern.sub('', raw_ai_response)

                        # 2. 首先，精确移除AI可能模仿的 <CURRENT_USER_MESSAGE_TO_REPLY...> 标签
                        formatted_ai_response = re.sub(r'<CURRENT_USER_MESSAGE_TO_REPLY.*?>', '', formatted_ai_response, flags=re.IGNORECASE)

                        # 3. 接着，使用新的清理函数移除所有括号 () 和 [] 及其内容，这也会处理掉 (向 @用户 回复): 格式
                        formatted_ai_response = regex_service.clean_ai_output(formatted_ai_response)
                        
                        # 4. 移除Discord旧版表情符号代码
                        discord_emoji_pattern = re.compile(r':\w+:')
                        formatted_ai_response = discord_emoji_pattern.sub(r'', formatted_ai_response)

                        # 4. 替换自定义表情符号
                        for pattern, emojis in EMOJI_MAPPINGS:
                            if isinstance(emojis, list) and emojis:
                                selected_emoji = random.choice(emojis)
                                formatted_ai_response = pattern.sub(selected_emoji, formatted_ai_response)
                            elif isinstance(emojis, str):
                                formatted_ai_response = pattern.sub(emojis, formatted_ai_response)
                        
                        blacklist_marker = "<blacklist>"
                        if formatted_ai_response.endswith(blacklist_marker):
                            formatted_ai_response = formatted_ai_response[:-len(blacklist_marker)].strip()
                            try:
                                ban_duration_minutes = random.randint(5, 10)
                                expires_at = datetime.now() + timedelta(minutes=ban_duration_minutes)
                                await db_manager.add_to_blacklist(user_id, guild_id, expires_at)
                                log.info(f"用户 {user_id} 因不当请求被拉黑 {ban_duration_minutes} 分钟。")
                                await affection_service.decrease_affection_on_blacklist(user_id, guild_id)
                            except Exception as e:
                                log.error(f"拉黑用户 {user_id} 时出错: {e}")
                        
                        log.info(f"即将为用户 {user_id} 返回AI回复: {formatted_ai_response}")
                        return formatted_ai_response
                    
                    elif response.prompt_feedback and response.prompt_feedback.block_reason:
                        log.warning(f"用户 {user_id} 的请求被 API 密钥 #{self.current_key_index} 的安全策略阻止，原因: {response.prompt_feedback.block_reason}")
                        return "抱歉，你的消息似乎触发了安全限制，我无法回复。请换个说法试试？"
                    
                    else:
                        # Log more details for debugging when response.parts is empty
                        log.warning(
                            f"API 密钥 #{self.current_key_index} 未能为用户 {user_id} 生成有效回复。"
                            f"Prompt Feedback: block_reason='{response.prompt_feedback.block_reason if response.prompt_feedback else 'N/A'}', "
                            f"safety_ratings='{response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'}'. "
                            f"Response Candidates: {getattr(response, 'candidates', 'N/A')}. "
                            f"将尝试下一个密钥。"
                        )
                        try:
                            problematic_request_body = json.dumps(final_conversation, indent=2, ensure_ascii=False, default=serialize_parts)
                            log.warning(f"导致空回复的请求体详情:\n{problematic_request_body}")
                        except Exception as e:
                            log.error(f"序列化问题请求体用于日志记录时失败: {e}")
                
                except (google_exceptions.InternalServerError, google_exceptions.ServiceUnavailable, google_exceptions.ResourceExhausted) as e:
                    log.warning(f"API 密钥 #{self.current_key_index} 遇到可重试的API错误: {e}. 将尝试下一个密钥。")
                    continue
            
            log.error(f"所有 API 密钥都未能为用户 {user_id} 生成有效回复。")
            return "哎呀，我好像没太明白你的意思呢～可以再说清楚一点吗？✨"
                
        except Exception as e:
            log.error(f"生成AI回复时出现意外错误: {e}")
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "limit" in error_msg:
                return "类脑娘今天累啦,明天再来找她玩吧～"
            elif "network" in error_msg or "timeout" in error_msg or "connect" in error_msg:
                return "类脑娘的...网络...似乎有些不稳定，请稍后...再试～"
            elif "image" in error_msg or "mime" in error_msg:
                return "呜哇,我无法识别这张图片呢，请尝试其他图片～"
            elif "400" in error_msg or "invalid" in error_msg:
                return "类脑娘收到了看不懂的东西，请检查消息内容～"
            else:
                return "抱歉，类脑娘有些晕晕的，请稍后再试～ "
    
    async def clear_user_context(self, user_id: int, guild_id: int):
        """清除指定用户的对话上下文"""
        await db_manager.clear_ai_conversation_context(user_id, guild_id)
        log.info(f"已清除用户 {user_id} 在服务器 {guild_id} 的对话上下文")
    
    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return len(self.clients) > 0

# 全局实例
gemini_service = GeminiService()
