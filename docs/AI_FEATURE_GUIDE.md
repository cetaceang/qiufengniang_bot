# AI聊天功能使用指南

## 功能概述

为Odysseia Guidance Bot添加了基于Gemini 2.5 flash-lite模型的AI聊天功能，支持：
- @mention自动回复
- 用户独立的对话上下文管理
- 数据库存储对话历史
- 可配置的系统提示词

## 安装依赖

首先安装新增的依赖：

```bash
pip install google-generativeai
```

或者使用requirements.txt更新：

```bash
pip install -r requirements.txt
```

## 环境变量配置

在`.env`文件中添加Gemini API密钥：

```env
# Gemini AI配置
GEMINI_API_KEY="你的_Gemini_API_密钥"
```

获取Gemini API密钥：
1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 创建API密钥
3. 复制到`.env`文件中

## 功能使用

### 1. @mention回复
直接在Discord中@mention机器人即可开始对话：

```
@OdysseiaBot 你好，能帮我介绍一下这个社区吗？
```

### 2. 命令功能

#### 清除对话上下文
```
!clear_context
!清除上下文
```

#### 查看AI状态
```
!ai_status
!ai状态
```

## 数据库结构

新增了两个数据库表：

### ai_conversation_contexts
存储用户对话上下文：
- `user_id`: 用户ID
- `guild_id`: 服务器ID  
- `conversation_history`: 对话历史(JSON格式)
- `last_updated`: 最后更新时间

### ai_prompts
存储AI提示词配置：
- `guild_id`: 服务器ID
- `prompt_name`: 提示词名称
- `prompt_content`: 提示词内容
- `is_active`: 是否激活

## 提示词配置

默认提示词位于`config/prompts.py`，包含：
- `SYSTEM_PROMPT`: 系统角色提示词
- `WELCOME_PROMPT`: 欢迎消息
- `ERROR_PROMPT`: 错误处理提示词
- `UNKNOWN_PROMPT`: 未知问题提示词

## 测试功能

运行测试脚本验证功能：

```bash
python test_ai_function.py
```

## 故障排除

### 常见问题

1. **AI服务不可用**
   - 检查`GEMINI_API_KEY`环境变量是否正确设置
   - 确认网络连接正常

2. **数据库错误**
   - 检查数据库文件权限
   - 确认数据库表结构正确创建

3. **回复超时**
   - Gemini API调用可能需要几秒钟时间
   - 网络状况会影响响应速度

### 日志查看

查看日志了解详细错误信息：
```python
import logging
logging.basicConfig(level=logging.INFO)
```

## 性能优化

- 使用线程池处理同步API调用
- 对话上下文限制为最近5轮对话
- 数据库连接使用连接池管理

## 自定义配置

### 修改系统提示词

编辑`config/prompts.py`中的`SYSTEM_PROMPT`来改变AI的行为和语气。

### 添加自定义提示词

通过数据库管理命令添加服务器特定的提示词：

```python
await db_manager.set_ai_prompt(guild_id, "custom_prompt", "你的自定义提示词内容")
```

## 安全考虑

- AI回复内容经过提示词过滤
- 对话历史存储在本地数据库
- 支持清除用户对话上下文
- 错误处理机制防止服务中断

## 扩展功能

未来可以扩展的功能：
- 多语言支持
- 情感分析
- 内容审核
- 对话统计分析