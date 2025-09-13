# -*- coding: utf-8 -*-

import re

class RegexService:
    """
    一个专门用于处理和清理文本中特定模式的的服务。
    """

    def clean_ai_output(self, text: str) -> str:
        """
        清理AI模型的输出文本。
        - 移除 () 和 [] 及其内部内容。
        - 移除全角/半角括号。
        """
        if not isinstance(text, str):
            return ""

        # 匹配 (), （）
        text = re.sub(r'[\(（][^)）]*[\)）]:?\s*', '', text)
        # 匹配 [], 【】
        text = re.sub(r'[\[【][^\]】]*[\]】]:?\s*', '', text)
        return text.strip()

    def clean_user_input(self, text: str) -> str:
        """
        清理用户的输入文本。
        - 移除 (), [], <> 及其内部内容。
        - 移除全角/半角括号和尖括号。
        """
        if not isinstance(text, str):
            return ""

        # 匹配 (), （）
        text = re.sub(r'[\(（][^)）]*[\)）]:?\s*', '', text)
        # 匹配 [], 【】
        text = re.sub(r'[\[【][^\]】]*[\]】]:?\s*', '', text)
        # 匹配 <>
        text = re.sub(r'[<][^>]*[>]:?\s*', '', text)
        
        return text.strip()

# 全局实例
regex_service = RegexService()