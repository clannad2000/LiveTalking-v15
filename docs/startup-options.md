# 容器启动方式说明

## 当前配置

项目目录已完整映射到容器的 `/app` 目录，因此 `fix_and_start.sh` 脚本也包含在映射中，无需单独挂载。

## 启动方式选择

### 方式 1：使用启动脚本（当前配置）✅

**docker-compose.yaml 配置：**
```yaml
entrypoint: ["/bin/bash"]
command: ["/app/fix_and_start.sh"]
```

**优点：**
- 显示详细的启动信息
- 检查 Python 和 PyTorch 版本
- 验证 CUDA 可用性
- 便于调试和排查问题

**适用场景：**
- 开发环境
- 首次部署
- 需要诊断问题时

**启动日志示例：**
```
==========================================
LiveTalking v1.5 启动中...
==========================================
Python 版本: Python 3.10.12
工作目录: /app
CUDA 可用性检查...
PyTorch: 2.5.0
CUDA available: True
CUDA devices: 1
==========================================
启动应用...
==========================================
```

### 方式 2：直接启动（最简洁）

**docker-compose.yaml 配置：**
```yaml
# 注释掉或删除 entrypoint 和 command
# entrypoint: ["/bin/bash"]
# command: ["/app/fix_and_start.sh"]
```

这样会使用 Dockerfile 中的默认 CMD：
```dockerfile
CMD ["python3", "app.py"]
```

**优点：**
- 最简洁
- 启动最快
- 日志更干净

**适用场景：**
- 生产环境
- 已验证环境正常
- 不需要额外诊断信息

## 启动脚本的作用变化

### 旧版本（Conda + Pip 混用）

```bash
#!/bin/bash

# 检查是否已经修复过
if [ ! -f /tmp/pytorch_fixed ]; then
    echo "修复 PyTorch 符号问题..."
    conda run -n livetalking pip uninstall -y torch torchvision torchaudio
    conda run -n livetalking pip install torch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0
    touch /tmp/pytorch_fixed
    echo "PyTorch 修复完成"
fi

# 启动应用
export PATH=/opt/conda/envs/livetalking/bin:$PATH
cd /app
exec /opt/conda/envs/livetalking/bin/python app.py
```

**作用：**
- ❌ 修复 PyTorch 符号链接问题（每次启动都要检查）
- ❌ 激活 Conda 环境
- ✅ 启动应用

### 新版本（纯 Pip）

```bash
#!/bin/bash

echo "=========================================="
echo "LiveTalking v1.5 启动中..."
echo "=========================================="

# 显示环境信息
echo "Python 版本: $(python3 --version)"
echo "工作目录: $(pwd)"
echo "CUDA 可用性检查..."
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"

echo "=========================================="
echo "启动应用..."
echo "=========================================="

cd /app
exec python3 app.py
```

**作用：**
- ✅ 显示诊断信息（可选）
- ✅ 启动应用

**关键变化：**
- ❌ 不再需要"修复"功能
- ❌ 不再需要 Conda 环境激活
- ✅ 纯粹的信息展示和启动

## 推荐配置

### 开发环境

```yaml
# docker-compose.yaml
services:
  livetalking:
    build: .
    entrypoint: ["/bin/bash"]
    command: ["/app/fix_and_start.sh"]  # 使用启动脚本，显示诊断信息
    volumes:
      - .:/app
```

### 生产环境

```yaml
# docker-compose.yaml
services:
  livetalking:
    image: your-registry/livetalking:latest
    # 直接使用 Dockerfile 的 CMD，无需启动脚本
    volumes:
      - .:/app
    restart: unless-stopped
```

## 文件位置说明

### 旧配置（需要单独挂载）

```yaml
volumes:
  - .:/app
  - ./fix_and_start.sh:/fix_and_start.sh:ro  # ❌ 单独挂载到根目录
```

**问题：**
- 需要维护两个挂载点
- 脚本位置不直观（在根目录而不是 /app）

### 新配置（包含在项目映射中）✅

```yaml
volumes:
  - .:/app  # ✅ 整个项目映射，包含 fix_and_start.sh
```

**优势：**
- 只需一个挂载点
- 脚本位置直观（在 /app/fix_and_start.sh）
- 更容易维护

## 如何切换启动方式

### 从启动脚本切换到直接启动

1. 编辑 `docker-compose.yaml`：
```yaml
# 注释掉这两行
# entrypoint: ["/bin/bash"]
# command: ["/app/fix_and_start.sh"]
```

2. 重启容器：
```bash
docker-compose down
docker-compose up -d
```

### 从直接启动切换到启动脚本

1. 编辑 `docker-compose.yaml`：
```yaml
# 取消注释这两行
entrypoint: ["/bin/bash"]
command: ["/app/fix_and_start.sh"]
```

2. 重启容器：
```bash
docker-compose down
docker-compose up -d
```

## 总结

| 特性 | 旧版启动脚本 | 新版启动脚本 | 直接启动 |
|------|------------|------------|---------|
| 修复 PyTorch | ✅ 需要 | ❌ 不需要 | ❌ 不需要 |
| Conda 激活 | ✅ 需要 | ❌ 不需要 | ❌ 不需要 |
| 诊断信息 | ❌ 无 | ✅ 有 | ❌ 无 |
| 启动速度 | 慢（首次修复） | 快 | 最快 |
| 适用场景 | Conda 环境 | 开发/调试 | 生产环境 |
| 是否需要单独挂载 | ✅ 需要 | ❌ 不需要 | ❌ 不需要 |

**推荐：**
- 开发环境：使用新版启动脚本（当前配置）
- 生产环境：直接启动（注释掉 entrypoint 和 command）
