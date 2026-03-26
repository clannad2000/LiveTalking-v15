#!/bin/bash

# 启动脚本 - 纯 Python 环境，无需 conda

echo "=========================================="
echo "LiveTalking v1.5 启动中..."
echo "=========================================="

# 显示环境信息
echo "Python 版本: $(python3 --version)"
echo "工作目录: $(pwd)"
echo "CUDA 可用性检查..."
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA devices: {torch.cuda.device_count()}')" 2>/dev/null || echo "PyTorch 检查失败"

echo "=========================================="
echo "启动应用..."
echo "=========================================="

# 切换到应用目录并启动
cd /app
exec python3 app.py
