# 增加 OpenAI 支持的技术方案

本文档描述了一种侵入性最小、最模块化的方式为现有项目增加 OpenAI API 支持的技术方案。

## 核心目标

1. **支持 OpenAI API**: 在保留 Gemini 的基础上，新增对 OpenAI 模型的支持
2. **侵入性最小**: 仅修改 5 行现有代码
3. **混合服务**: 对话用 OpenAI，嵌入向量和安全评分继续用 Gemini
4. **可配置化**: 通过环境变量即可切换服务，零风险回退
5. **模块化设计**: 新增代码高度内聚，易于维护和扩展

## 方案对比

| 特性 | 适配器模式（原方案） | 路由器模式（推荐） |
|------|---------------------|------------------|
| 侵入性 | 中等（需要实现所有方法） | **最小（只修改5行）** |
| 灵活性 | 低（完全替换） | **高（可混合使用）** |
| 代码量 | 多（300+行） | **少（250行）** |
| 维护性 | 中等 | **高** |
| 扩展性 | 低 | **高（易添加新服务）** |

## 架构设计：路由器模式

### 架构图
```
调用者 (chat_service.py 等)
    ↓
gemini_service (实际是 AIServiceRouter)
    ↓
根据配置和功能路由
    ├─→ OpenAIService (对话生成)
    └─→ GeminiService (嵌入向量、安全评分、其他功能)
```

### 核心优势
- **零改动调用方**: 所有现有的 `await gemini_service.generate_response()` 调用保持不变
- **灵活路由**: 不同功能可以使用最合适的 AI 服务
- **成本优化**: 嵌入向量继续用便宜的 Gemini，对话用高质量的 OpenAI

## 实施步骤

### 步骤 1: 创建 OpenAI 服务类

**文件**: `src/chat/services/openai_service.py`

```python
import os
import logging
from typing import Optional, Dict, List, Any
from openai import AsyncOpenAI
import json

log = logging.getLogger(__name__)

class OpenAIService:
    """OpenAI 服务类，专注于对话生成"""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")

        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.client = AsyncOpenAI(api_key=self.api_key)

        # 复用现有的工具注册系统
        from src.chat.features.tools.tool_registry import tool_registry
        from src.chat.features.tools.services.tool_service import ToolService

        self.tool_service = ToolService()
        self.tools = tool_registry.get_all_tools_schema()

        log.info(f"OpenAIService 初始化完成，使用模型: {self.model}")

    def set_bot(self, bot):
        """注入 Discord Bot 实例"""
        self.bot = bot
        log.info("Discord Bot 实例已注入 OpenAIService")

    async def generate_response(
        self,
        user_id: int,
        guild_id: int,
        message: str,
        replied_message: Optional[str] = None,
        images: Optional[List[Dict]] = None,
        user_name: str = "用户",
        channel_context: Optional[List[Dict]] = None,
        world_book_entries: Optional[List[Dict]] = None,
        personal_summary: Optional[str] = None,
        affection_status: Optional[Dict[str, Any]] = None,
        user_profile_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """生成对话回复（核心方法）"""
        try:
            # 1. 构建对话历史（复用 prompt_service）
            from src.chat.services.prompt_service import prompt_service

            final_conversation = prompt_service.build_chat_prompt(
                user_name=user_name,
                message=message,
                replied_message=replied_message,
                images=images,
                channel_context=channel_context,
                world_book_entries=world_book_entries,
                affection_status=affection_status,
                personal_summary=personal_summary,
                user_profile_data=user_profile_data,
            )

            # 2. 转换为 OpenAI 格式
            messages = self._convert_to_openai_format(final_conversation)

            # 3. 准备工具定义（如果有）
            tools = None
            if self.tools:
                tools = self._convert_tools_to_openai_format(self.tools)

            # 4. 调用 OpenAI API
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                temperature=1.1,  # 与 Gemini 配置保持一致
                max_tokens=3000,
            )

            response_message = completion.choices[0].message

            # 5. 处理工具调用
            if response_message.tool_calls:
                # 执行工具调用
                tool_results = await self._handle_tool_calls(
                    response_message.tool_calls, user_id
                )

                # 将工具结果添加到对话
                messages.append(response_message)
                for tool_result in tool_results:
                    messages.append(tool_result)

                # 再次调用获取最终回复
                final_completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=1.1,
                )

                raw_response = final_completion.choices[0].message.content
            else:
                raw_response = response_message.content

            # 6. 后处理（复用现有逻辑）
            formatted_response = await self._post_process_response(
                raw_response, user_id, guild_id
            )

            # 7. 更新对话历史
            from src.chat.services.context_service import context_service
            await context_service.update_user_conversation_history(
                user_id, guild_id, message, raw_response
            )

            return formatted_response

        except Exception as e:
            log.error(f"OpenAI API 调用失败: {e}", exc_info=True)
            return "哎呀，我好像遇到了一点问题，请稍后再试～"

    # ... 其他辅助方法 ...
```

### 步骤 2: 创建 AI 服务路由器

**文件**: `src/chat/services/ai_service_router.py`

```python
import os
import logging
from typing import Any

log = logging.getLogger(__name__)

class AIServiceRouter:
    """AI 服务路由器 - 根据配置和功能路由到不同的 AI 服务"""

    def __init__(self):
        self.chat_provider = os.getenv("AI_CHAT_PROVIDER", "gemini").lower()

        # 始终需要 GeminiService（用于嵌入向量等功能）
        from src.chat.services.gemini_service import GeminiService
        self.gemini_service = GeminiService()

        # 根据配置决定是否需要 OpenAI
        self.openai_service = None
        if self.chat_provider == "openai":
            try:
                from src.chat.services.openai_service import OpenAIService
                self.openai_service = OpenAIService()
                log.info("已启用 OpenAI 服务用于对话生成")
            except Exception as e:
                log.error(f"初始化 OpenAI 服务失败: {e}")
                log.info("回退到 Gemini 服务")
                self.chat_provider = "gemini"

    def set_bot(self, bot):
        """注入 Discord Bot 实例到所有服务"""
        self.gemini_service.set_bot(bot)
        if self.openai_service:
            self.openai_service.set_bot(bot)

    async def generate_response(self, *args, **kwargs):
        """路由对话生成请求"""
        if self.chat_provider == "openai" and self.openai_service:
            return await self.openai_service.generate_response(*args, **kwargs)
        else:
            return await self.gemini_service.generate_response(*args, **kwargs)

    # 以下方法始终使用 Gemini
    async def generate_embedding(self, *args, **kwargs):
        """生成嵌入向量 - 始终使用 Gemini"""
        return await self.gemini_service.generate_embedding(*args, **kwargs)

    async def generate_text(self, *args, **kwargs):
        """简单文本生成 - 使用 Gemini"""
        return await self.gemini_service.generate_text(*args, **kwargs)

    async def generate_simple_response(self, *args, **kwargs):
        """生成简单回复 - 使用 Gemini"""
        return await self.gemini_service.generate_simple_response(*args, **kwargs)

    async def generate_thread_praise(self, *args, **kwargs):
        """生成帖子夸奖 - 使用 Gemini"""
        return await self.gemini_service.generate_thread_praise(*args, **kwargs)

    async def generate_text_with_image(self, *args, **kwargs):
        """图文生成 - 使用 Gemini"""
        return await self.gemini_service.generate_text_with_image(*args, **kwargs)

    async def generate_confession_response(self, *args, **kwargs):
        """生成忏悔回应 - 使用 Gemini"""
        return await self.gemini_service.generate_confession_response(*args, **kwargs)

    async def summarize_for_rag(self, *args, **kwargs):
        """RAG 查询重写 - 使用 Gemini"""
        return await self.gemini_service.summarize_for_rag(*args, **kwargs)

    # 其他方法直接转发到 Gemini
    def __getattr__(self, name):
        """对于未明确定义的方法，转发到 Gemini 服务"""
        return getattr(self.gemini_service, name)
```

### 步骤 3: 修改 gemini_service.py（仅末尾）

在文件末尾（第 1049 行）修改：

```python
# 原代码：
# gemini_service = GeminiService()

# 新代码：
import os
if os.getenv("AI_CHAT_PROVIDER", "gemini").lower() == "openai":
    from .ai_service_router import AIServiceRouter
    gemini_service = AIServiceRouter()
else:
    gemini_service = GeminiService()
```

### 步骤 4: 更新配置文件

**requirements.txt** 添加：
```
openai>=1.0.0
```

**.env.example** 添加：
```
# --- AI 服务配置 ---
# 选择对话生成服务: gemini 或 openai
AI_CHAT_PROVIDER="gemini"

# OpenAI 配置（当 AI_CHAT_PROVIDER=openai 时需要）
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o"
```

### 步骤 5: 添加配置常量（可选）

**src/chat/config/chat_config.py** 添加：
```python
# --- OpenAI 配置 ---
OPENAI_CHAT_CONFIG = {
    "temperature": 1.1,
    "max_tokens": 3000,
}
```

## 配置指南

### 启用 OpenAI
1. 在 `.env` 文件中设置：
   ```
   AI_CHAT_PROVIDER="openai"
   OPENAI_API_KEY="你的-openai-api-key"
   OPENAI_MODEL="gpt-4o"  # 可选，默认 gpt-4o
   ```

2. 重启服务

### 切换回 Gemini
1. 修改 `.env`：
   ```
   AI_CHAT_PROVIDER="gemini"
   ```
   或直接删除/注释掉该行

2. 重启服务

## 技术细节

### 工具调用适配
- Gemini 格式：`function_declarations`
- OpenAI 格式：`tools` 参数，每个工具需要 `type: "function"`
- 工具调用响应格式转换已在 `OpenAIService` 中处理

### 安全机制
- `<warn>` 标记：通过 prompt 引导，OpenAI 也能输出
- 后处理逻辑（`_post_process_response`）完全复用
- 嵌入向量的安全评分继续使用 Gemini

### 成本优化
- 对话生成：使用 OpenAI（高质量）
- 嵌入向量：使用 Gemini（便宜）
- 小功能：使用 Gemini（稳定、便宜）

## 测试建议

1. **基础对话测试**
   - 发送普通消息，验证回复正常
   - 测试带图片的消息
   - 测试回复消息功能

2. **工具调用测试**
   - 测试 `get_user_avatar` 等工具
   - 验证工具调用结果正确返回

3. **安全机制测试**
   - 发送可能触发警告的内容
   - 验证 `<warn>` 标记正常工作

4. **混合服务测试**
   - 测试 RAG 检索（应使用 Gemini 嵌入）
   - 测试其他小功能（应继续正常工作）

## 总结

这个方案实现了：
- ✅ 侵入性最小（只修改 5 行）
- ✅ 高度模块化（新代码独立）
- ✅ 灵活配置（环境变量控制）
- ✅ 混合服务（各取所长）
- ✅ 易于维护和扩展

预计实施时间：4-6 小时（包括测试）
