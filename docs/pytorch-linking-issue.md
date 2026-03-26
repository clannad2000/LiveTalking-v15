# PyTorch 动态链接库问题说明

## 问题描述

在容器中运行应用时，可能会遇到类似以下的错误：

```
ImportError: /opt/conda/envs/livetalking/lib/python3.10/site-packages/face_alignment/_C.so: 
undefined symbol: _ZN5torch3jit17parseSchemaOrNameERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE
```

## 根本原因

### 1. PyTorch 2.x 库结构变化

- **PyTorch 1.x**：提供统一的 `libtorch.so`
- **PyTorch 2.x**：分离为 `libtorch_cpu.so` 和 `libtorch_cuda.so`

### 2. C++ 扩展编译时的链接问题

某些 Python 包（如 `face_alignment`）包含 C++ 扩展，这些扩展在编译时会链接到 PyTorch 的 C++ 库：

```cpp
// face_alignment 的 C++ 扩展在编译时链接
#include <torch/extension.h>
// 编译器期望找到 libtorch.so
```

当这些包通过 pip 安装时：
1. pip 会尝试编译 C++ 扩展
2. 编译器查找 `libtorch.so`（旧版本命名）
3. 但 PyTorch 2.x 只提供 `libtorch_cpu.so` 或 `libtorch_cuda.so`
4. 导致链接失败或运行时符号未定义

### 3. 动态链接器搜索路径

Linux 动态链接器（ld.so）按以下顺序搜索共享库：
1. `LD_LIBRARY_PATH` 环境变量指定的路径
2. `/etc/ld.so.cache` 缓存的路径
3. 默认路径（`/lib`, `/usr/lib` 等）

如果 PyTorch 库不在这些路径中，就会出现 "undefined symbol" 错误。

## 解决方案

### 方案 1：符号链接（当前采用）

创建向后兼容的符号链接：

```bash
# 在 PyTorch 库目录创建符号链接
ln -sf libtorch_cuda.so libtorch.so

# 在 conda 库目录也创建链接，方便系统查找
ln -sf /path/to/torch/lib/libc10.so /opt/conda/envs/livetalking/lib/libc10.so
```

**优点**：
- 简单直接
- 兼容性好
- 不需要修改代码

**缺点**：
- 需要在构建时处理
- 如果 PyTorch 更新可能需要重新处理

### 方案 2：设置 LD_LIBRARY_PATH

将 PyTorch 库路径添加到动态链接器搜索路径：

```dockerfile
ENV LD_LIBRARY_PATH=/opt/conda/envs/livetalking/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH}
```

**优点**：
- 不需要创建符号链接
- 更灵活

**缺点**：
- 如果某些扩展硬编码了 `libtorch.so`，仍然会失败
- 需要确保环境变量在所有执行上下文中生效

### 方案 3：使用 PyTorch 的 wheel 包（推荐用于生产）

直接使用 PyTorch 官方的 wheel 包，而不是 conda 安装：

```dockerfile
RUN pip install torch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 \
    --index-url https://download.pytorch.org/whl/cu124
```

**优点**：
- 官方打包，兼容性更好
- 避免 conda 和 pip 混用的问题

**缺点**：
- 下载速度可能较慢（国内）
- 包体积较大

### 方案 4：预编译 C++ 扩展

在构建镜像时预编译所有 C++ 扩展：

```dockerfile
RUN conda run -n livetalking python -c "import face_alignment; print('face_alignment loaded successfully')"
```

**优点**：
- 可以在构建时发现问题
- 运行时性能更好

**缺点**：
- 构建时间更长
- 需要完整的编译环境

## 当前实现

我们采用 **方案 1 + 方案 2** 的组合：

1. **创建符号链接**：确保向后兼容
2. **设置 LD_LIBRARY_PATH**：让动态链接器能找到库
3. **设置 LD_PRELOAD**：预加载 MKL 库，解决 Intel MKL 冲突

```dockerfile
# 创建符号链接
RUN TORCH_LIB=/opt/conda/envs/livetalking/lib/python3.10/site-packages/torch/lib \
 && ln -sf libtorch_cuda.so "$TORCH_LIB/libtorch.so" \
 && ln -sf "$TORCH_LIB/libc10.so" /opt/conda/envs/livetalking/lib/libc10.so

# 设置环境变量
ENV LD_LIBRARY_PATH=/opt/conda/envs/livetalking/lib/python3.10/site-packages/torch/lib:${LD_LIBRARY_PATH}
ENV LD_PRELOAD=/opt/conda/envs/livetalking/lib/libmkl_core.so:/opt/conda/envs/livetalking/lib/libmkl_sequential.so
ENV MKL_THREADING_LAYER=GNU
```

## 验证方法

构建镜像后，可以通过以下命令验证：

```bash
# 进入容器
docker exec -it livetalking-v15 bash

# 激活环境
conda activate livetalking

# 检查 PyTorch 库
ls -la /opt/conda/envs/livetalking/lib/python3.10/site-packages/torch/lib/ | grep libtorch

# 测试导入
python -c "import torch; import face_alignment; print('Success!')"

# 检查动态链接
ldd /opt/conda/envs/livetalking/lib/python3.10/site-packages/face_alignment/_C.so
```

## 参考资料

- [PyTorch C++ API](https://pytorch.org/cppdocs/)
- [Linux Dynamic Linking](https://tldp.org/HOWTO/Program-Library-HOWTO/shared-libraries.html)
- [Conda vs Pip](https://www.anaconda.com/blog/understanding-conda-and-pip)
