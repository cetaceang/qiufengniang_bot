import yaml
import re
import os
from typing import Optional, List, Dict, Any

class WorldBookService:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(WorldBookService, cls).__new__(cls)
        return cls._instance

    def __init__(self, file_path: str = 'src/world_book/data/knowledge.yml'):
        self.file_path = file_path
        self.entries = self._load_entries()

    def _load_entries(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.file_path):
            # In a real application, you might want to log this error.
            print(f"Error: World book file not found at {self.file_path}")
            return []
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            try:
                # yaml.safe_load_all returns a generator, so we convert it to a list.
                return list(yaml.safe_load_all(f))
            except yaml.YAMLError as e:
                print(f"Error parsing YAML file: {e}")
                return []

    def find_entries(self, context: List[Dict[str, Any]], user_message: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        在用户消息和历史上下文中查找所有匹配的世界书条目。
        用户消息中的匹配项具有最高的优先级。
        上下文中的匹配项优先级由条目自身的基础优先级和它在上下文中的位置共同决定。
        """
        triggered_entries = {}  # {entry_id: dynamic_priority}
        triggered_entry_data = {} # {entry_id: entry}

        # 1. 首先处理用户当前消息，给予最高优先级
        if user_message:
            for entry in self.entries:
                if self._is_triggered(entry, user_message):
                    entry_id = entry.get('id')
                    # 为用户消息中的匹配项设置一个非常高的基础优先级
                    base_priority = entry.get('priority', 0)
                    dynamic_priority = base_priority + 1000  # 确保它高于任何上下文匹配
                    
                    if entry_id not in triggered_entries or dynamic_priority > triggered_entries[entry_id]:
                        triggered_entries[entry_id] = dynamic_priority
                        triggered_entry_data[entry_id] = entry

        # 2. 然后处理历史上下文
        # 从旧到新遍历上下文，越新的消息索引越大
        for i, message in enumerate(context):
            message_content = self._get_message_content(message)
            if not message_content:
                continue

            for entry in self.entries:
                if self._is_triggered(entry, message_content):
                    entry_id = entry.get('id')
                    # 动态优先级 = 基础优先级 + 位置奖励 (i)
                    base_priority = entry.get('priority', 0)
                    dynamic_priority = base_priority + i

                    # 如果条目已触发，只有当新的动态优先级更高时才更新
                    if entry_id not in triggered_entries or dynamic_priority > triggered_entries[entry_id]:
                        triggered_entries[entry_id] = dynamic_priority
                        triggered_entry_data[entry_id] = entry

        if not triggered_entries:
            return []
        
        # 根据动态优先级对条目ID进行排序
        sorted_entry_ids = sorted(triggered_entries.keys(), key=lambda eid: triggered_entries[eid], reverse=True)
        
        # 构建并返回排序后的条目列表
        return [triggered_entry_data[eid] for eid in sorted_entry_ids]

    def _get_message_content(self, message: Dict[str, Any]) -> str:
        """从消息字典中提取并拼接内容字符串"""
        if not isinstance(message, dict) or 'parts' not in message:
            return ""
        
        parts = message.get('parts', [])
        if isinstance(parts, list):
            return " ".join(str(p) for p in parts)
        else:
            return str(parts)

    def _is_triggered(self, entry: Dict[str, Any], content: str) -> bool:
        """检查单个条目是否被给定的内容触发"""
        trigger = entry.get('trigger', {})
        trigger_type = trigger.get('type')
        trigger_value = trigger.get('value')
        entry_id = entry.get('id')

        if not trigger_type or not trigger_value or not entry_id:
            return False

        if trigger_type == 'keyword':
            return trigger_value.lower() in content.lower()
        elif trigger_type == 'regex':
            try:
                return bool(re.search(trigger_value, content, re.IGNORECASE))
            except re.error as e:
                print(f"世界书条目 (id: {entry_id}) 中的正则表达式错误: {e}")
                return False
        return False

# Singleton instance for easy access across the application
world_book_service = WorldBookService()
