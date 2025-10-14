from google.genai import types
import discord
import inspect
from typing import Optional
import logging
from src.chat.features.tools.tool_registry import tool_registry

log = logging.getLogger(__name__)

class ToolService:
    """
    一个负责执行 Gemini 模型请求的工具函数调用的服务。
    它充当调度程序，使用 ToolRegistry 查找并运行适当的工具。
    """

    async def execute_tool_call(self, tool_call: types.FunctionCall, bot: Optional[discord.Client] = None, author_id: Optional[int] = None) -> types.Part:
        """
        执行单个工具调用，并以可发送回 Gemini 模型的格式返回结果。
        这个版本支持向工具传递上下文（如 bot 实例、author_id）并处理多模态输出。

        Args:
            tool_call: 来自 Gemini API 响应的函数调用对象。
            bot: 可选的 discord.Client 实例，用于需要与 Discord API 交互的工具。
            author_id: 可选的当前消息作者的 Discord ID。

        Returns:
            一个格式化为 FunctionResponse 的 Part 对象，其中包含工具的输出。
        """
        tool_name = tool_call.name
        try:
            # 从注册中心检索工具的实现
            tool_info = tool_registry.get_tool(tool_name)
            tool_function = tool_info["function"]

            # 提取工具调用的参数
            tool_args = dict(tool_call.args)

            # 检查工具函数签名，并根据需要注入上下文依赖
            sig = inspect.signature(tool_function)
            if 'bot' in sig.parameters:
                tool_args['bot'] = bot
            if 'author_id' in sig.parameters and author_id is not None:
                tool_args['author_id'] = author_id

            # 执行工具函数
            result = await tool_function(**tool_args)
            log.info(f"工具 '{tool_name}' 已执行，参数: {tool_args}, 返回结果: {result}")
            
            part = types.Part.from_function_response(
                name=tool_name,
                response={"result": result} # 根据文档，response 需要一个包含 "result" 键的字典
            )
            log.info(f"正在将构造好的 Part 返回给 gemini_service: {part}")
            return part

        except ValueError as e:
            # 处理找不到工具的情况
            log.error(f"找不到工具 '{tool_name}'。", exc_info=True)
            return types.Part.from_function_response(
                name=tool_name,
                response={"error": f"找不到工具: {str(e)}"}
            )
        except Exception as e:
            # 处理工具执行期间的任何其他异常
            print(f"执行工具 '{tool_name}' 期间发生意外错误: {e}")
            log.error(f"执行工具 '{tool_name}' 时发生意外错误。", exc_info=True)
            return types.Part.from_function_response(
                name=tool_name,
                response={"error": f"执行工具时发生意外错误: {str(e)}"}
            )