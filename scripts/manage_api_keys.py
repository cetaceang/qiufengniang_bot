import os
import json
import re
import sys

# 将项目根目录添加到 sys.path，以便可以导入项目模块（如果需要）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

REPUTATION_FILE = os.path.join(ROOT_DIR, "data", "key_reputations.json")
ENV_FILE = os.path.join(ROOT_DIR, ".env")


def load_reputations():
    """加载信誉分数文件"""
    if not os.path.exists(REPUTATION_FILE):
        print(f"错误: 信誉文件未找到于 {REPUTATION_FILE}")
        return None
    try:
        with open(REPUTATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"错误: 读取或解析信誉文件失败: {e}")
        return None


def get_keys_from_env():
    """从 .env 文件中获取 GEMINI_API_KEYS"""
    if not os.path.exists(ENV_FILE):
        print(f"错误: .env 文件未找到于 {ENV_FILE}")
        return None, None

    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r"^GEMINI_API_KEYS=(.*)$", content, re.MULTILINE)
        if not match:
            print("错误: 在 .env 文件中未找到 'GEMINI_API_KEYS'。")
            return None, None

        keys_str = match.group(1).strip()
        # 移除可能存在的引号
        if keys_str.startswith('"') and keys_str.endswith('"'):
            keys_str = keys_str[1:-1]

        keys = [key.strip() for key in keys_str.split(",") if key.strip()]
        return keys, content
    except IOError as e:
        print(f"错误: 读取 .env 文件失败: {e}")
        return None, None


def main():
    """主执行函数"""
    print("--- API 密钥信誉管理脚本 ---")

    reputations = load_reputations()
    if reputations is None:
        return

    current_keys, env_content = get_keys_from_env()
    if current_keys is None:
        return

    print(f"当前 .env 文件中共有 {len(current_keys)} 个密钥。")
    print(f"已加载 {len(reputations)} 个密钥的信誉数据。")

    try:
        threshold_str = input(
            "请输入要移除的密钥的信誉分数阈值 (例如, 输入 10 将移除所有分数低于 10 的密钥): "
        )
        threshold = int(threshold_str)
    except ValueError:
        print("错误: 无效的数字输入。操作已中止。")
        return

    keys_to_remove = {
        key
        for key, score in reputations.items()
        if key in current_keys and score < threshold
    }

    if not keys_to_remove:
        print(f"没有找到信誉分数低于 {threshold} 的密钥。无需任何操作。")
        return

    print("\n警告: 以下密钥的信誉分数低于阈值，将被从 .env 文件中移除:")
    for key in keys_to_remove:
        # 为了安全，只显示部分密钥
        print(f"  - ...{key[-4:]} (分数: {reputations.get(key, 'N/A')})")

    confirm = input("\n您确定要永久移除以上所列的密钥吗? (y/n): ").lower()

    if confirm != "y":
        print("操作已取消。")
        return

    # 从当前密钥列表中过滤掉要移除的密钥
    updated_keys = [key for key in current_keys if key not in keys_to_remove]
    updated_keys_str = ",".join(updated_keys)

    # 使用正则表达式替换 .env 文件中的行
    new_env_content = re.sub(
        r"^GEMINI_API_KEYS=.*$",
        f'GEMINI_API_KEYS="{updated_keys_str}"',
        env_content,
        flags=re.MULTILINE,
    )

    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(new_env_content)
        print(f"\n成功! 已从 .env 文件中移除 {len(keys_to_remove)} 个密钥。")
        print(f"剩余 {len(updated_keys)} 个密钥。")
    except IOError as e:
        print(f"错误: 写入 .env 文件失败: {e}")


if __name__ == "__main__":
    main()
