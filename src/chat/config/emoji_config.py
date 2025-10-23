# -*- coding: utf-8 -*-

"""
表情符号配置文件
用于定义AI输出文本到Discord自定义表情符号的映射关系
使用正则表达式进行匹配和替换
"""

import re

# 定义表情符号映射
# 格式: [(正则表达式, Discord表情符号), ...]
EMOJI_MAPPINGS = [
    (re.compile(r"\<微笑\>"), ["<:xianhua:1430791695745945671>"]),
    (re.compile(r"\<伤心\>"), ["<:shang_xin:1430792098642137259>"]),
    (re.compile(r"\<生气\>"), ["<:shen_qi:1430793384192245761>"]),
    (re.compile(r"\<乖巧\>"), ["<:guai_qiao:1430792822268755978>"]),
    (re.compile(r"\<傲娇\>"), ["<:ao_jiao:1430791778264420395>"]),
    (re.compile(r"\<尴尬赞\>"), ["<:ganga_zan:1430797709752799262>"]),
    (re.compile(r"\<赞\>"), ["<:good:1430792560699244564>"]),
    (re.compile(r"\<吃瓜\>"), ["<:chi_gua:1430792314195939348>"]),
    (re.compile(r"\<偷笑\>"), ["<:tou_xiao:1430797814065270905>"]),
    (re.compile(r"\<无语\>"), ["<:wu_yu:1430793312436097055>"]),
    (re.compile(r"\<鬼脸\>"), ["<:ghost_face:1430800459895013387>"]),
    (re.compile(r"\<鄙视\>"), ["<:bi_shi:1430792966695293011>"]),
    (re.compile(r"\<思考\>"), ["<:ping_jing:11430792178564599860>"]),
    (re.compile(r"\<害羞\>"), ["<:shy:11430792049325510707>"]),
]

# --- 活动专属表情 ---

# 万圣节 2025 - 幽灵派系
_HALLOWEEN_GHOST_EMOJI_MAPPINGS = [
    (re.compile(r"\<害羞\>"), ["<:hai_xiu:1430196858394902683>"]),
    (re.compile(r"\<害怕\>"), ["<:hai_pa:1430196738240806973>"]),
    (re.compile(r"\<开心\>"), ["<:kai_xin:1430196805194223707>"]),
    (re.compile(r"\<紧张\>"), ["<:jing_zhang:1430197186636812378>"]),
    (re.compile(r"\<鲜花\>"), ["<:xian_hua:1430197117703684219>"]),
    (re.compile(r"\<生气\>"), ["<:sheng_qi:1430197007183642724>"]),
    (re.compile(r"\<呆\>"), ["<:dai:1430196922039402548>"]),
]

# --- 派系表情总配置 ---
# 结构: { "event_id": { "faction_id": MAPPING_LIST } }
FACTION_EMOJI_MAPPINGS = {
    "halloween_2025": {
        "ghost": _HALLOWEEN_GHOST_EMOJI_MAPPINGS,
        # 未来可以轻松在这里添加其他派系，例如:
        # "vampire": _HALLOWEEN_VAMPIRE_EMOJI_MAPPINGS,
    }
}
