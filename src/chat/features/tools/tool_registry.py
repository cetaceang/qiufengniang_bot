import functools
from typing import Callable, Dict, Any
import logging

log = logging.getLogger(__name__)

class ToolRegistry:
    """
    A central registry for managing and discovering tools for the Gemini model.
    Tools are registered using the @register_tool decorator.
    """
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, schema: Dict[str, Any], func: Callable):
        """
        Registers a tool by its name, schema, and implementation function.
        """
        if name in self._tools:
            log.warning(f"工具 '{name}' 正在被重新定义。")
        else:
            log.info(f"工具 '{name}' 已成功注册。")
        self._tools[name] = {"schema": schema, "function": func}

    def get_tool(self, name: str) -> Dict[str, Any]:
        """
        Retrieves a tool's schema and function by its name.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry.")
        return tool

    def get_all_tools_schema(self) -> list[Dict[str, Any]]:
        """
        Returns a list of schemas for all registered tools.
        This is the format required by the Gemini API.
        """
        return [tool["schema"] for tool in self._tools.values()]

# Global instance of the registry
tool_registry = ToolRegistry()

def register_tool(name: str, schema: Dict[str, Any]):
    """
    A decorator to register a function as a tool in the global tool_registry.

    Args:
        name: The name of the tool, as it will be called by the model.
        schema: The function declaration schema for the tool.
    """
    def decorator(func: Callable):
        tool_registry.register(name, schema, func)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator