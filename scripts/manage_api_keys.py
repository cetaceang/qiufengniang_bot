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

        match = re.search(
            r"^GOOGLE_API_KEYS_LIST=(.*)$", content, re.MULTILINE | re.DOTALL
        )
        if not match:
            print("错误: 在 .env 文件中未找到 'GOOGLE_API_KEYS_LIST'。")
            return None, None

        keys_str = match.group(1).strip()
        # 移除可能存在的引号
        if keys_str.startswith('"') and keys_str.endswith('"'):
            keys_str = keys_str[1:-1]

        # 对每个分割后的 key 去除可能存在的引号
        keys = [
            key.strip().strip('"').strip("'")
            for key in keys_str.split(",")
            if key.strip()
        ]
        return keys, content
    except IOError as e:
        print(f"错误: 读取 .env 文件失败: {e}")
        return None, None


def main():
    """主执行函数"""
    # 检查是否提供了 'status' 参数，用于仅显示状态
    if len(sys.argv) > 1 and sys.argv[1].lower() == "status":
        print("--- 正在检查 API 密钥分数分布 ---")
        reputations = load_reputations()
        if reputations is None:
            return
        current_keys, _ = get_keys_from_env()
        if current_keys is None:
            return

        score_counts = {}
        for key, data in reputations.items():
            if key in current_keys:
                # 确保 data 是字典并且有 'reputation' 键
                if isinstance(data, dict) and "reputation" in data:
                    score = data["reputation"]
                    score_counts[score] = score_counts.get(score, 0) + 1

        # --- 将详细调试信息写入文件 ---
        try:
            with open("debug_output.txt", "w", encoding="utf-8") as f:
                f.write("--- 详细调试信息 ---\n")
                reputation_keys = reputations.keys()

                f.write("\n逐一检查从 .env 文件加载的密钥:\n")
                for key_from_env in current_keys:
                    is_found = key_from_env in reputation_keys
                    f.write(
                        f"  - 检查: >{key_from_env}< (长度: {len(key_from_env)}) | 是否在 reputation.json 中找到: {is_found}\n"
                    )

                f.write("\n逐一检查从 key_reputations.json 加载的密钥:\n")
                for key_from_json in reputation_keys:
                    is_found = key_from_json in current_keys
                    f.write(
                        f"  - 检查: >{key_from_json}< (长度: {len(key_from_json)}) | 是否在 .env 中找到: {is_found}\n"
                    )

                f.write("\n--- 调试结束 ---\n")
            print(
                "\n[诊断] 详细调试信息已写入项目根目录下的 debug_output.txt 文件。请检查该文件。\n"
            )
        except Exception as e:
            print(f"[诊断] 写入调试文件时出错: {e}")
        # --- 调试代码结束 ---

        if score_counts:
            print("\n--- 当前密钥分数分布 ---")
            # 按分数排序，确保是数字类型
            sorted_scores = sorted(
                [s for s in score_counts.keys() if isinstance(s, (int, float))]
            )
            for score in sorted_scores:
                print(f"  - 分数: {score}, 密钥数量: {score_counts[score]}")
            print("-------------------------")
        else:
            print("没有找到与当前 .env 中密钥匹配的信誉数据。")
        return  # 仅显示状态后退出

    print("--- API 密钥信誉管理脚本 ---")

    reputations = load_reputations()
    if reputations is None:
        return

    current_keys, env_content = get_keys_from_env()
    if current_keys is None:
        return

    print(f"当前 .env 文件中共有 {len(current_keys)} 个密钥。")
    print(f"已加载 {len(reputations)} 个密钥的信誉数据。")

    # 统计并显示每个分数的密钥数量
    score_counts = {}
    for key, data in reputations.items():
        if key in current_keys:
            if isinstance(data, dict) and "reputation" in data:
                score = data["reputation"]
                score_counts[score] = score_counts.get(score, 0) + 1

    if score_counts:
        print("\n--- 当前密钥分数分布 ---")
        # 按分数排序以获得更好的可读性
        # 按分数排序，确保是数字类型
        sorted_scores = sorted(
            [s for s in score_counts.keys() if isinstance(s, (int, float))]
        )
        for score in sorted_scores:
            print(f"  - 分数: {score}, 密钥数量: {score_counts[score]}")
        print("-------------------------\n")

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
        for key, data in reputations.items()
        if key in current_keys
        and isinstance(data, dict)
        and data.get("reputation", float("inf")) < threshold
    }

    if not keys_to_remove:
        print(f"没有找到信誉分数低于 {threshold} 的密钥。无需任何操作。")
        return

    print(
        f"\n警告: 发现 {len(keys_to_remove)} 个密钥的信誉分数低于阈值，将被从 .env 文件中移除:"
    )
    for key in keys_to_remove:
        reputation_value = reputations.get(key, {})
        score_display = (
            reputation_value.get("reputation", "N/A")
            if isinstance(reputation_value, dict)
            else "格式错误"
        )
        print(f"  - {key} (分数: {score_display})")

    confirm = input("\n您确定要永久移除以上所列的密钥吗? (y/n): ").lower()

    if confirm != "y":
        print("操作已取消。")
        return

    # 从当前密钥列表中过滤掉要移除的密钥
    updated_keys = [key for key in current_keys if key not in keys_to_remove]
    updated_keys_str = ",".join(updated_keys)

    # 使用正则表达式替换 .env 文件中的行
    new_env_content = re.sub(
        r"^GOOGLE_API_KEYS_LIST=.*$",
        f'GOOGLE_API_KEYS_LIST="{updated_keys_str}"',
        env_content,
        flags=re.MULTILINE | re.DOTALL,
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
