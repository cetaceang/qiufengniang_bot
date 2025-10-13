import re
from src.chat.config.prompts import SYSTEM_PROMPT
from src.chat.config.emoji_config import EMOJI_MAPPINGS


def replace_emojis(text: str) -> str:
    """
    根据 emoji_config.py 中的映射规则，
    将文本中的自定义表情占位符（如 <微笑>）替换为对应的 Discord 自定义表情（如 <:xianhua:12345>）。
    """
    for pattern, replacement_list in EMOJI_MAPPINGS:
        if replacement_list:
            # 替换内容必须是字符串，因此我们从列表中取出第一个元素
            text = pattern.sub(replacement_list[0], text)
    return text


def extract_persona_prompt(system_prompt: str) -> str:
    """
    从 SYSTEM_PROMPT 中提取 <character> 标签内的全部内容，
    用于构建 /投喂 命令的提示词。
    """
    # 使用正则表达式提取 <character> 标签及其所有内容
    match = re.search(r"<character>.*?</character>", system_prompt, re.DOTALL)

    if match:
        # 如果找到匹配项，则返回整个 <character>...</character> 块
        return match.group(0)
    else:
        # 如果没有找到，返回一个空字符串以避免意外注入规则
        return ""


def get_core_persona() -> str:
    """
    为暖贴功能，从 SYSTEM_PROMPT 中提取特定的、精简的人设信息。
    此函数现在与 get_thread_commentor_persona 功能相同。
    """
    return get_thread_commentor_persona()


def get_thread_commentor_persona() -> str:
    """
    为暖贴功能，从 SYSTEM_PROMPT 中提取特定的、精简的人设信息。
    使用独立的标签来确保提取的准确性。
    包括:
    - <core_identity>
    - <markdown_guidelines>
    - <emoji_guidelines>
    """
    # 提取 <core_identity>
    core_identity_match = re.search(
        r"<core_identity>.*?</core_identity>", SYSTEM_PROMPT, re.DOTALL
    )
    core_identity = core_identity_match.group(0) if core_identity_match else ""

    # 提取 <markdown_guidelines>
    markdown_guidelines_match = re.search(
        r"<markdown_guidelines>.*?</markdown_guidelines>", SYSTEM_PROMPT, re.DOTALL
    )
    markdown_guidelines = (
        markdown_guidelines_match.group(0) if markdown_guidelines_match else ""
    )

    # 提取 <emoji_guidelines>
    emoji_guidelines_match = re.search(
        r"<emoji_guidelines>.*?</emoji_guidelines>", SYSTEM_PROMPT, re.DOTALL
    )
    emoji_guidelines = emoji_guidelines_match.group(0) if emoji_guidelines_match else ""

    # 按照要求的格式拼接
    parts = [core_identity, markdown_guidelines, emoji_guidelines]

    # 过滤掉空字符串并用换行符连接
    final_persona = "\n\n".join(part for part in parts if part)

    return final_persona
