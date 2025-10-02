# 配置管理API文档

## 概述

LiveTalking提供了一组配置管理API，允许用户实时修改和读取应用程序的配置参数，而无需重启服务器。这些API特别适用于动态调整模型、头像、LLM设置等参数。

## API列表

### 1. 获取配置

**GET /api/config**

获取应用程序内存中的配置参数。可以获取整个配置、特定部分的配置或特定配置项的值。

**参数**:
- `section` (可选): 配置部分的名称，如 `server` 或 `llm`
- `key` (可选): 配置项的名称，如 `model` 或 `avatar_id`

**响应示例**:
```json
{
  "success": true,
  "data": {
    "model": "musetalkv15",
    "avatar_id": "avator_3_480p",
    "llm_type": "coze"
  }
}
```

### 2. 更新单个配置

**POST /api/config**

更新应用程序内存中的单个配置项。请注意，通过API修改的配置参数**不会**写入配置文件，只在当前运行会话中生效。

**请求体**:
```json
{
  "section": "server",
  "key": "model",
  "value": "wav2lip"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "Config updated successfully"
}
```

### 3. 批量更新配置

**POST /api/config/bulk**

批量更新应用程序内存中的多个配置项。请注意，通过API修改的配置参数**不会**写入配置文件，只在当前运行会话中生效。

**请求体**:
```json
{
  "updates": {
    "server": {
      "model": "musetalk",
      "avatar_id": "avator_1",
      "llm_type": "opai"
    },
    "llm": {
      "opai": {
        "api_key": "your_new_api_key",
        "model": "gpt-3.5-turbo"
      }
    }
  }
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "All configs updated successfully",
  "failed": []
}
```

### 4. 获取模型配置

**GET /api/config/model**

获取内存中与模型相关的所有配置，包括使用的模型、头像、LLM类型和LLM配置。

**响应示例**:
```json
{
  "success": true,
  "data": {
    "model": "musetalkv15",
    "avatar_id": "avator_3_480p",
    "llm_type": "coze",
    "llm_config": {
      "api_token": "your_api_token",
      "workflow_id": "your_workflow_id",
      "base_url": "https://api.coze.cn"
    }
  }
}
```

### 5. 更新模型配置

**POST /api/config/model**

更新系统内存中的模型相关配置参数。请注意，通过API修改的配置参数**不会**写入配置文件，只在当前运行会话中生效。

**请求体**:
```json
{
  "model": "wav2lip",
  "avatar_id": "avator_2",
  "llm_type": "opai",
  "llm_config": {
    "api_key": "your_new_api_key",
    "model": "gpt-3.5-turbo",
    "base_url": "https://api.openai.com/v1"
  }
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "Model config updated successfully",
  "failed": []
}
```

## 支持的配置参数

### 模型配置
- `model`: 使用的模型类型，可选值包括 `musetalk`、`musetalkv15`、`wav2lip`、`ultralight`
- `avatar_id`: 使用的头像ID，对应 `data/avatars/` 目录下的子目录名称
- `llm_type`: LLM服务类型，可选值包括 `coze`、`opai`
- `llm_config`: LLM服务的详细配置，根据 `llm_type` 的不同而有所差异
  - 对于 `coze` 类型: `api_token`、`workflow_id`、`base_url` 等
  - 对于 `opai` 类型: `api_key`、`model`、`base_url`、`system_prompt` 等

## 使用示例

### 使用curl更新模型配置

```bash
curl -X POST http://localhost:8010/api/config/model \-H "Content-Type: application/json" \-d '{"model": "wav2lip", "avatar_id": "avator_1"}'
```

### 使用JavaScript获取当前配置

```javascript
fetch('http://localhost:8010/api/config/model')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log('当前使用的模型:', data.data.model);
      console.log('当前使用的头像:', data.data.avatar_id);
      console.log('当前使用的LLM类型:', data.data.llm_type);
    }
  });
```

## 注意事项

1. 配置更新后会立即保存到配置文件中，但某些配置（如模型类型）可能需要重启应用程序才能生效。

2. 更新LLM配置时，请确保提供了所有必要的参数，如API密钥等。

3. 为了系统安全，请谨慎处理包含敏感信息的配置，如API密钥。

4. 建议在更新配置前备份原始配置文件 `conf/app_config.yaml`。