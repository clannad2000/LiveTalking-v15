# 构建命令示例:
# docker build -t livetalkingv15:latest .
# 如需代理: docker build --build-arg http_proxy=http://proxy:port --build-arg https_proxy=http://proxy:port -t livetalkingv15:latest .

# 使用 runtime 镜像（比 devel 小 3-4GB）
# runtime 包含 CUDA runtime 和 cuDNN，足够运行 PyTorch
ARG BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM ${BASE_IMAGE}

# ============================================================================
# 容器内最终目录结构:
# ============================================================================
# /usr/local/                              - Python 系统安装目录
#   ├── bin/python3.10                     - Python 解释器
#   └── lib/python3.10/site-packages/      - Python 包
#
# /app/                                    - 应用主目录 (通过 volume 挂载宿主机项目目录)
#   ├── app.py                             - 主程序入口
#   ├── requirements.txt                   - Python 依赖列表
#   ├── conf/                              - 配置文件目录
#   ├── data/                              - 数据目录
#   ├── models/                            - AI 模型目录 (在宿主机预先下载)
#   ├── scripts/                           - 脚本目录
#   ├── ssl/                               - SSL 证书目录
#   └── *.py                               - 各种 Python 模块文件
# ============================================================================

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# 通过 build-arg 传代理，不要写死在镜像里
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY}

# 安装系统依赖（Ubuntu 22.04 自带 Python 3.10）
# 添加 build-essential 以防某些 Python 包需要编译（体积增加约 200MB，但比 devel 镜像小得多）
RUN apt-get update -yq --fix-missing \
 && apt-get install -yq --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    build-essential \
    pkg-config \
    wget \
    cmake \
    curl \
    git \
    vim \
    ffmpeg \
    libasound-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    unzip \
 && rm -rf /var/lib/apt/lists/*

# 设置 Python 3.10 为默认版本
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
 && update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
 && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# 先复制 requirements，最大化缓存
COPY requirements.txt /app/requirements.txt

# 安装 PyTorch (使用官方 wheel，避免编译)
RUN pip3 install \
    torch==2.5.0 \
    torchvision==0.20.0 \
    torchaudio==2.5.0 \
    --index-url https://download.pytorch.org/whl/cu124

# 配置 pip 镜像源并安装其他依赖
RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
 && pip3 install --no-cache-dir -r /app/requirements.txt

# 验证安装并检查 PyTorch 库
RUN echo "=== Verifying PyTorch installation ===" \
 && python3 -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}')" \
 && echo "=== Checking PyTorch libraries ===" \
 && TORCH_LIB=$(python3 -c "import torch; import os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))") \
 && echo "Torch lib directory: $TORCH_LIB" \
 && ls -lh "$TORCH_LIB" | grep -E "libtorch|libc10" || echo "No torch libraries found (this is OK for wheel installation)" \
 && echo "=== Testing imports ===" \
 && python3 -c "import cv2; print(f'OpenCV version: {cv2.__version__}')" \
 && python3 -c "import numpy; print(f'NumPy version: {numpy.__version__}')" \
 && echo "=== Installation verification complete ==="

EXPOSE 8010

# 设置环境变量
# 注意：使用 pip 安装的 PyTorch wheel 包通常不需要额外的 LD_LIBRARY_PATH 设置
# 因为库已经正确打包在 wheel 中
ENV PYTHONPATH=/app:${PYTHONPATH}

CMD ["python3", "app.py"]
