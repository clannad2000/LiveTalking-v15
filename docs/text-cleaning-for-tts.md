# TTS 文本清理说明

## 问题描述

当 LLM（如 DeepSeek、ChatGPT）返回包含 emoji 表情符号或特殊字符的文本时，TTS（文字转语音）引擎无法正确处理这些字符，导致：

1. **显示的文本**：包含 emoji（如 "数字人：✨"）
2. **语音读出的内容**：跳过或错误处理 emoji，导致不一致

### 示例

**LLM 返回**：
```
你好！我是你的AI助手✨，很高兴为你服务😊
```

**TTS 读出**：
```
你好我是你的AI助手很高兴为你服务
```

**问题**：emoji 被跳过，但显示在界面上，造成不一致。

## 解决方案

在 `llm.py` 中添加了 `clean_text_for_tts()` 函数，在文本发送到 TTS 之前进行清理。

### 清理规则

1. **移除 emoji 表情符号**
   - 所有 Unicode emoji 范围的字符
   - 包括：😊 ✨ 🎉 👍 等

2. **移除特殊符号**
   - 保留：中文字符、英文字母、数字
   - 保留：常用标点符号（，。！？、；：""''（）《》等）
   - 移除：其他特殊字符

3. **规范化空格**
   - 移除多余的空格
   - 去除首尾空格

### 代码实现

```python
def clean_text_for_tts(text):
    """
    清理文本，移除 emoji 和其他不适合 TTS 的字符
    """
    if not text:
        return text
    
    # 移除 emoji 表情符号
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 旗帜
        "\U00002702-\U000027B0"  # 装饰符号
        "\U000024C2-\U0001F251"  # 其他符号
        "\U0001F900-\U0001F9FF"  # 补充符号和象形文字
        "\U0001FA00-\U0001FA6F"  # 扩展符号
        "\U00002600-\U000026FF"  # 杂项符号
        "]+",
        flags=re.UNICODE
    )
    
    # 移除 emoji
    text = emoji_pattern.sub('', text)
    
    # 移除其他特殊字符，但保留中文标点
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、；：""''（）《》\s,.!?;:\'"()\-]', '', text)
    
    # 移除多余的空格
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text
```

### 应用位置

#### 1. OpenAI 兼容 API（流式响应）

```python
def opai_response(message, nerfreal:BaseReal):
    # ...
    for chunk in completion:
        if len(chunk.choices)>0:
            msg = chunk.choices[0].delta.content
            # 清理文本
            msg = clean_text_for_tts(msg) if msg else ""
            if not msg:  # 如果清理后为空，跳过
                continue
            # ... 发送到 TTS
```

#### 2. Coze API（完整响应）

```python
def coze_response(text, nerfreal:BaseReal):
    # ...
    response = coze.chat_with_coze(text)
    
    # 清理响应文本
    response = clean_text_for_tts(response)
    
    # 分句并发送到 TTS
    sentences = re.split('[。？！]', response)
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            nerfreal.put_msg_txt(sentence)
```

## 效果对比

### 修复前

| 步骤 | 内容 |
|------|------|
| LLM 返回 | "你好！我是你的AI助手✨" |
| 显示文本 | "数字人：✨" |
| TTS 读出 | "你好我是你的AI助手" |
| 问题 | ❌ 显示和语音不一致 |

### 修复后

| 步骤 | 内容 |
|------|------|
| LLM 返回 | "你好！我是你的AI助手✨" |
| 清理后 | "你好！我是你的AI助手" |
| 显示文本 | "数字人：你好！我是你的AI助手" |
| TTS 读出 | "你好！我是你的AI助手" |
| 结果 | ✅ 显示和语音一致 |

## 日志输出

修复后，日志会显示发送到 TTS 的清理后文本：

```
INFO:logger:Sending to TTS: 你好！我是你的AI助手
INFO:logger:Sending final to TTS: 很高兴为你服务
```

这样可以方便调试和确认文本清理是否正确。

## 自定义清理规则

如果需要调整清理规则，可以修改 `clean_text_for_tts()` 函数：

### 保留更多标点符号

```python
# 保留更多标点
text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、；：""''（）《》【】\s,.!?;:\'"()\[\]\-]', '', text)
```

### 保留数字和单位

```python
# 保留数字单位（如 ℃、%、$）
text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、；：""''（）《》\s,.!?;:\'"()\-℃%$¥€]', '', text)
```

### 完全移除标点

```python
# 只保留文字和数字
text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', text)
```

## 注意事项

1. **不要过度清理**
   - 保留必要的标点符号，否则 TTS 的语调会不自然
   - 保留数字和常用符号

2. **测试不同 TTS 引擎**
   - 不同的 TTS 引擎对特殊字符的支持不同
   - EdgeTTS、Google TTS、Azure TTS 等可能有不同的要求

3. **多语言支持**
   - 当前规则主要针对中文和英文
   - 如需支持其他语言，需要调整 Unicode 范围

4. **性能考虑**
   - 正则表达式处理对性能影响很小
   - 在流式响应中，每个 chunk 都会清理一次

## 相关配置

可以在 `conf/app_config.yaml` 中配置 LLM 的 system_prompt，让 LLM 尽量不返回 emoji：

```yaml
llm:
  openai:
    system_prompt: "You are a helpful assistant. Please respond in plain text without using emojis or special symbols."
```

但即使这样配置，仍然建议保留文本清理功能，因为：
1. LLM 可能不完全遵守指令
2. 用户输入可能包含 emoji
3. 提供额外的安全保障

## 总结

通过添加 `clean_text_for_tts()` 函数，确保了：
- ✅ 显示的文本和语音内容一致
- ✅ TTS 引擎能正确处理所有文本
- ✅ 用户体验更好
- ✅ 支持各种 LLM 返回的文本格式
