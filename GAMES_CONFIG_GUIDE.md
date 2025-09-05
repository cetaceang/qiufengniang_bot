# 抽王八游戏配置指南

本文档详细说明了如何配置抽王八游戏的文本和图片URL。

## 配置文件位置
所有配置都在 `src/games/config/text_config.py` 文件中

## 文本配置说明

### 1. AI策略开局文本配置 (AI_OPENING_TEXTS)
```python
AI_OPENING_TEXTS = {
    "LOW": "类脑娘看起来有些迷茫，眼神飘忽不定...",
    "MEDIUM": "类脑娘目光专注，似乎在认真思考策略...", 
    "HIGH": "你感到类脑娘目光如炬，你有些紧张...",
    "SUPER": "类脑娘进入超级模式，眼神中闪烁着数据流..."
}
```

### 2. AI策略缩略图URL配置 (AI_THUMBNAIL_URLS)
```python
AI_THUMBNAIL_URLS = {
    "LOW": "https://example.com/images/ai_low.png",
    "MEDIUM": "https://example.com/images/ai_medium.png", 
    "HIGH": "https://example.com/images/ai_high.png",
    "SUPER": "https://example.com/images/ai_super.png",
    "DEFAULT": "https://example.com/images/default.png"
}
```

### 3. AI反应图片URL配置 (AI_REACTION_URLS)
```python
AI_REACTION_URLS = {
    "LOW": "https://example.com/images/reaction_low.png",
    "MEDIUM": "https://example.com/images/reaction_medium.png", 
    "HIGH": "https://example.com/images/reaction_high.png",
    "SUPER": "https://example.com/images/reaction_super.png",
    "DEFAULT": "https://example.com/images/reaction_default.png"
}
```

### 4. 游戏界面文本配置 (GAME_TEXTS)
```python
GAME_TEXTS = {
    "TITLE": "🎴 抽王八游戏",
    "ERROR_TITLE": "❌ 游戏不存在",
    "GAME_OVER_TITLE": "🎮 游戏结束",
    "CURRENT_TURN_PLAYER": "👤 你的回合",
    "CURRENT_TURN_AI": "🤖 AI的回合",
    "REMAINING_CARDS": "剩余牌数",
    "PLAYER_HAND": "你的手牌",
    "AI_HAND": "AI的手牌",
    "CARDS_COUNT": "张牌",
    "INSTRUCTION": "请使用下面的按钮选择要抽的牌\n⚠️ 凑齐👑和8️⃣就会输！",
    "WAITING_AI": "等待AI抽牌...",
    "PLAYER_WIN": "🎉 恭喜你赢了！",
    "AI_WIN": "😈 AI赢了！",
    "FINAL_HAND_PLAYER": "你的最终手牌",
    "FINAL_HAND_AI": "AI的最终手牌",
    "RESTART_PROMPT": "点击重新开始按钮再玩一局！"
}
```

### 5. 确认面板文本配置 (CONFIRM_TEXTS)
```python
CONFIRM_TEXTS = {
    "MODAL_TITLE": "确认抽牌",
    "SPECIAL_CARD_WARNING": "⚠️ 警告！这是一张特殊牌 {}, 抽中可能会输！确认要抽吗？",
    "NORMAL_CARD_CONFIRM": "确认要抽这张牌吗？牌面: {}",
    "CONFIRM_BUTTON": "确认抽这张",
    "CANCEL_BUTTON": "不抽这张",
    "DRAW_CANCELLED": "❌ 抽牌已取消",
    "CHOOSE_OTHER": "❌ 抽牌已取消，请选择其他牌"
}
```

### 6. 反应界面文本配置 (REACTION_TEXTS)
```python
REACTION_TEXTS = {
    "TITLE": "🤖 类脑娘的反应",
    "FOOTER": "类脑娘正在观察你的行动..."
}
```

### 7. 错误消息配置 (ERROR_TEXTS)
```python
ERROR_TEXTS = {
    "GAME_ENDED": "游戏已结束或不存在",
    "NOT_YOUR_TURN": "现在不是你的回合",
    "INVALID_CARD_INDEX": "无效的牌索引",
    "GENERAL_ERROR": "❌ 处理操作时出现错误，请稍后再试。",
    "DRAW_ERROR": "❌ 处理抽牌时出现错误"
}
```

### 8. AI回合消息配置 (AI_TURN_TEXTS)
```python
AI_TURN_TEXTS = {
    "PREFIX": "🤖 AI的回合: {}"
}
```

## 图片URL配置说明

### 缩略图URL
- **低级AI**: `AI_THUMBNAIL_URLS["LOW"]`
- **中级AI**: `AI_THUMBNAIL_URLS["MEDIUM"]`
- **高级AI**: `AI_THUMBNAIL_URLS["HIGH"]`
- **超级AI**: `AI_THUMBNAIL_URLS["SUPER"]`
- **默认**: `AI_THUMBNAIL_URLS["DEFAULT"]`

### 反应图片URL
- **低级反应**: `AI_REACTION_URLS["LOW"]`
- **中级反应**: `AI_REACTION_URLS["MEDIUM"]`
- **高级反应**: `AI_REACTION_URLS["HIGH"]`
- **超级反应**: `AI_REACTION_URLS["SUPER"]`
- **默认反应**: `AI_REACTION_URLS["DEFAULT"]`

## 修改步骤

1. 打开 `src/games/config/text_config.py` 文件
2. 找到需要修改的配置项
3. 替换为您想要的文本或URL
4. 保存文件
5. 重启机器人即可生效

## 注意事项

- 所有URL必须是有效的图片链接
- 文本中可以包含emoji表情
- 格式化字符串使用 `{}` 作为占位符
- 修改后需要重启机器人才能生效

## 游戏特性

- 游戏消息为临时消息（ephemeral）
- 游戏面板持续15分钟
- 抽王八模式：凑齐👑和8️⃣就输
- 根据AI策略显示不同的开局文本
- 抽牌前有确认面板
- 根据抽牌结果显示类脑娘反应