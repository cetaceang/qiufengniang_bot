# -*- coding: utf-8 -*-

"""
商店商品配置文件
用于定义商店中所有商品的详细信息和价格。
"""

from src.chat.features.odysseia_coin.service.coin_service import (
    PERSONAL_MEMORY_ITEM_EFFECT_ID, WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID,
    COMMUNITY_MEMBER_UPLOAD_EFFECT_ID, DISABLE_THREAD_COMMENTOR_EFFECT_ID,
    BLOCK_THREAD_REPLIES_EFFECT_ID, ENABLE_THREAD_COMMENTOR_EFFECT_ID,
    ENABLE_THREAD_REPLIES_EFFECT_ID
)

SHOP_ITEMS = [
    # name, description, price, category, target, effect_id
    ("枯萎向日葵", "购买后秋风娘不会再暖你的帖子", 0, "物品-给自己", "self", DISABLE_THREAD_COMMENTOR_EFFECT_ID),
    ("告示牌", "上面写着禁止通行,购买后秋风娘不会在你的帖子下面对话", 0, "物品-给自己", "self", BLOCK_THREAD_REPLIES_EFFECT_ID),
    ("魔法向日葵", "神奇的魔法向日葵!购买后秋风娘又会暖你的帖子了,友谊的魔法!。", 10, "物品-给自己", "self", ENABLE_THREAD_COMMENTOR_EFFECT_ID),
    ("通行许可", "一张官方签发的许可,购买后秋风娘可以在你的帖子下对话.并且可以设置秋风娘的活跃时间哦", 10, "物品-给自己", "self", ENABLE_THREAD_REPLIES_EFFECT_ID),
    ("咖啡", "喝下后你感觉精力变强了一点...不过好像只有24h", 50, "食品-给自己", "self", "coffee_chat_cooldown"),
    ("名片", "输入你的信息,并解锁与秋风娘的专属长期记忆,让她真正地记住你。", 100, "物品-给自己", "self", PERSONAL_MEMORY_ITEM_EFFECT_ID),
    ("知识纸条", "写下你对社区的了解（仅限无关社区成员的信息），帮助秋风娘更好地认识世界。", 0, "物品-贡献", "self", WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID),
    ("社区成员档案上传", "上传其他社区成员的档案信息，上传的信息将被正确识别为社区成员。", 100, "物品-贡献", "self", COMMUNITY_MEMBER_UPLOAD_EFFECT_ID),
    ("草莓小蛋糕", "精致的奶油草莓蛋糕", 15, "食品-给秋风娘", "ai", None),
    ("巧克力曲奇", "香浓可口的巧克力曲奇饼干", 12, "食品-给秋风娘", "ai", None),
    ("抹茶马卡龙", "精致的法式抹茶马卡龙", 18, "食品-给秋风娘", "ai", None),
    ("布丁", "滑嫩香甜的焦糖布丁", 10, "食品-给秋风娘", "ai", None),
    ("水果沙拉", "新鲜多样的水果拼盘", 8, "食品-给秋风娘", "ai", None),
    ("向日葵", "代表阳光的花朵,不觉得和秋风娘很配吗?", 8, "礼物-给秋风娘", "ai", None),
    ("泰迪熊", "承载着回忆的泰迪熊", 20, "礼物-给秋风娘", "ai", None),
    ("明信片", "旅途中随手买的明信片", 3, "礼物-给秋风娘", "ai", None),
    ("星空投影灯", "可以投射美丽星空的夜灯", 25, "礼物-给秋风娘", "ai", None),
    ("音乐盒", "播放轻柔音乐的精美音乐盒", 30, "礼物-给秋风娘", "ai", None),
]