# Docker 基础镜像选择指南

## NVIDIA CUDA 镜像变体

NVIDIA 提供了多种 CUDA 镜像变体，大小和功能各不相同：

### 1. base 镜像

```dockerfile
FROM nvidia/cuda:12.4.1-base-ubuntu22.04
```

**大小**：~1.5 GB

**包含内容**：
- Ubuntu 基础系统
- CUDA runtime 库（最小集）

**缺少**：
- ❌ cuDNN
- ❌ 编译工具
- ❌ CUDA 开发头文件

**适用场景**：
- 只运行预编译的 CUDA 应用
- 不使用深度学习框架

**本项目**：❌ 不适用（缺少 cuDNN）

### 2. runtime 镜像 ✅ 推荐

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
```

**大小**：~2.5-3 GB

**包含内容**：
- Ubuntu 基础系统
- CUDA runtime 库（完整）
- cuDNN runtime 库
- NCCL（多GPU通信）

**缺少**：
- ❌ CUDA 编译工具（nvcc）
- ❌ CUDA 开发头文件
- ❌ cuDNN 开发头文件

**适用场景**：
- 运行 PyTorch/TensorFlow（使用预编译 wheel）
- 不需要编译 CUDA 代码
- 大部分 Python 包有预编译版本

**本项目**：✅ 推荐（节省 3-4GB）

### 3. devel 镜像

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
```

**大小**：~6-8 GB

**包含内容**：
- runtime 镜像的所有内容
- CUDA 编译工具（nvcc, nvprof 等）
- CUDA 开发头文件
- cuDNN 开发头文件
- 示例代码

**适用场景**：
- 需要编译 CUDA 代码
- 需要从源码编译 PyTorch
- 开发 CUDA 扩展

**本项目**：⚠️ 过度（浪费 3-4GB 空间）

## 本项目的选择

### 当前配置：runtime + build-essential

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get install -y build-essential python3.10-dev
```

**总大小**：~3.5 GB（比 devel 小 3-4GB）

**优势**：
1. ✅ 包含 cuDNN，可运行 PyTorch
2. ✅ 添加 build-essential（~200MB），可编译 Python C++ 扩展
3. ✅ 比 devel 镜像小 50%
4. ✅ 满足所有依赖需求

**为什么需要 build-essential？**

某些 Python 包可能需要编译 C++ 扩展：
- `face_alignment`：可能需要编译 C++ 代码
- `ninja`：构建工具
- `numba`：JIT 编译器

虽然这些包通常有预编译的 wheel，但添加 build-essential 可以：
- 确保兼容性
- 支持从源码安装（如果 wheel 不可用）
- 只增加 ~200MB，相比 devel 仍然小很多

## 镜像大小对比

| 配置 | 基础镜像 | 系统包 | PyTorch | Python 依赖 | 总计 | 节省 |
|------|---------|--------|---------|------------|------|------|
| devel | 6.5 GB | 0.5 GB | 2.5 GB | 1.0 GB | ~10.5 GB | - |
| runtime + build | 2.5 GB | 0.7 GB | 2.5 GB | 1.0 GB | ~6.7 GB | **3.8 GB** |
| runtime only | 2.5 GB | 0.5 GB | 2.5 GB | 1.0 GB | ~6.5 GB | 4.0 GB |

## 如何进一步减小镜像

### 1. 多阶段构建（最优）

```dockerfile
# 构建阶段：使用 devel 镜像编译
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04 AS builder
RUN pip install --no-cache-dir -r requirements.txt

# 运行阶段：使用 runtime 镜像
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
```

**优势**：
- 最终镜像只包含 runtime
- 编译工具不在最终镜像中

**劣势**：
- 构建复杂
- 需要仔细处理依赖路径

### 2. 使用 slim 基础镜像

```dockerfile
FROM python:3.10-slim
# 手动安装 CUDA runtime
```

**优势**：
- 基础镜像更小（~150MB）

**劣势**：
- 需要手动配置 CUDA
- 复杂度高
- 容易出错

### 3. 清理构建缓存

```dockerfile
RUN apt-get install -y build-essential \
 && pip install -r requirements.txt \
 && apt-get remove -y build-essential \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*
```

**优势**：
- 减少 ~200MB

**劣势**：
- 如果后续需要安装包会失败
- 不适合开发环境

## 推荐配置

### 开发环境

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
RUN apt-get install -y build-essential python3.10-dev
```

**理由**：
- 可以随时安装新包
- 可以编译 C++ 扩展
- 大小适中

### 生产环境

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
# 不安装 build-essential，依赖预编译 wheel
```

**理由**：
- 最小化攻击面
- 减少镜像大小
- 生产环境不应该编译代码

## 验证镜像大小

```bash
# 查看镜像大小
docker images | grep livetalking

# 查看镜像层
docker history livetalking-v15:latest

# 分析镜像内容
docker run --rm livetalking-v15:latest du -sh /usr/local/lib/python3.10
docker run --rm livetalking-v15:latest du -sh /usr/local/cuda
```

## 总结

**当前选择**：`nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` + `build-essential`

**理由**：
1. ✅ 比 devel 小 **3.8 GB**（节省 36%）
2. ✅ 包含所有运行时依赖
3. ✅ 可以编译 Python C++ 扩展
4. ✅ 配置简单，不易出错
5. ✅ 适合开发和生产环境

**如果需要更小**：
- 移除 build-essential（-200MB）
- 使用多阶段构建（-500MB）
- 但增加复杂度和维护成本

**权衡**：在镜像大小和易用性之间，我们选择了一个平衡点。
