# 配置说明

## 快速开始

1. 复制配置模板文件：
```bash
cp conf/app_config.yaml.template conf/app_config.yaml
```

2. 编辑 `conf/app_config.yaml`，填入你的配置信息

## 配置项说明

### 服务器配置 (server)

- `fps`: 音频帧率，必须为 50
- `avatar_id`: 使用的数字人模型，位于 `data/avatars/` 目录
- `batch_size`: 推理批次大小，默认 25
- `tts`: TTS 服务类型
  - `edgetts`: 微软 Edge TTS（免费，推荐）
  - `xtts`: XTTS 服务
  - `gpt-sovits`: GPT-SoVITS 服务
  - `cosyvoice`: CosyVoice 服务
- `model`: 使用的模型
  - `musetalkv15`: MuseTalk v1.5（推荐）
  - `wav2lip`: Wav2Lip
  - `ultralight`: 超轻量模型
- `transport`: 传输方式
  - `webrtc`: WebRTC（推荐）
  - `rtcpush`: RTC 推流
  - `virtualcam`: 虚拟摄像头
- `listenport`: Web 服务监听端口，默认 8010
- `llm_type`: LLM 类型
  - `openai`: OpenAI 兼容 API（支持 DeepSeek、通义千问等）
  - `coze`: 扣子 Coze 工作流

### LLM 配置 (llm)

#### OpenAI 兼容 API 配置

```yaml
openai:
  api_key: "sk-your-api-key-here"  # 你的 API 密钥
  base_url: "https://api.deepseek.com/v1"  # API 地址
  model: "deepseek-chat"  # 模型名称
  system_prompt: "..."  # 系统提示词
  stream: true  # 是否使用流式输出
```

支持的服务：
- **DeepSeek**: `https://api.deepseek.com/v1`
- **OpenAI**: `https://api.openai.com/v1`
- **通义千问**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- 其他 OpenAI 兼容服务

#### Coze 配置

```yaml
coze:
  api_token: "pat_your_coze_token_here"  # Coze API 令牌
  workflow_id: "your_workflow_id_here"  # 工作流 ID
  base_url: "https://api.coze.cn"  # API 地址
```

## 获取 API 密钥

### DeepSeek
1. 访问 https://platform.deepseek.com/
2. 注册并登录
3. 在 API Keys 页面创建新密钥

### OpenAI
1. 访问 https://platform.openai.com/
2. 注册并登录
3. 在 API Keys 页面创建新密钥

### 通义千问
1. 访问 https://dashscope.aliyun.com/
2. 注册并登录
3. 在 API-KEY 管理页面创建新密钥

### Coze
1. 访问 https://www.coze.cn/
2. 创建工作流
3. 获取 API Token 和 Workflow ID

## 注意事项

⚠️ **重要**：
- 不要将包含真实 API 密钥的配置文件提交到 Git
- `conf/app_config.yaml` 已在 `.gitignore` 中排除
- 只提交 `conf/app_config.yaml.template` 模板文件

## 示例配置

### 使用 DeepSeek（推荐，性价比高）

```yaml
server:
  llm_type: "openai"

llm:
  openai:
    api_key: "sk-xxxxxxxxxxxxxxxx"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
```

### 使用 OpenAI

```yaml
server:
  llm_type: "openai"

llm:
  openai:
    api_key: "sk-xxxxxxxxxxxxxxxx"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4"
```

### 使用 Coze

```yaml
server:
  llm_type: "coze"

llm:
  coze:
    api_token: "pat_xxxxxxxxxxxxxxxx"
    workflow_id: "754xxxxxxxxxxxxxxx"
    base_url: "https://api.coze.cn"
```
