# Gemini思考预算功能整合计划

## 当前状态分析

项目已经有一个完善的Gemini服务实现，位于 [`src/chat/services/gemini_service.py`](src/chat/services/gemini_service.py)。当前对思考功能的处理：

```python
if 'flash' in self.model_name.lower():
    gen_config.thinking_config = types.ThinkingConfig(thinking_budget=0)
```

## 整合方案

### 1. 配置修改

**文件：** [`src/chat/config/chat_config.py`](src/chat/config/chat_config.py)

**修改内容：**
- 在 `GEMINI_CHAT_CONFIG` 中添加 `thinking_budget: 1024`
- 保持Flash模型的特殊处理（thinking_budget=0）

```python
GEMINI_CHAT_CONFIG = {
    "temperature": 1.1,
    "top_p": 0.97,
    "top_k": 50,
    "max_output_tokens": 300,
    "thinking_budget": 1024,  # 新增思考预算配置
}
```

### 2. 服务层修改

**文件：** [`src/chat/services/gemini_service.py`](src/chat/services/gemini_service.py)

**修改内容：**
- 移除第244-246行的Flash模型特殊处理
- 统一应用配置中的思考预算设置
- 保持Flash模型的向后兼容性

### 3. 功能说明

**思考预算配置选项：**
- `1024`: 启用标准思考功能
- `0`: 完全禁用思考
- `-1`: 动态思考（模型自动决定）
- 其他数值：自定义思考预算

## 实施步骤

1. 修改配置文件添加思考预算参数
2. 更新Gemini服务逻辑
3. 测试不同模型的思考功能
4. 验证向后兼容性

## 预期效果

- 非Flash模型（如gemini-2.5-pro）将启用思考功能
- Flash模型保持思考关闭以确保性能
- 提供统一的配置接口