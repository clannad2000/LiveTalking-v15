# Docker 部署指南

## 前置要求

1. **Docker 和 Docker Compose**
   - Docker Desktop (Windows/Mac) 或 Docker Engine (Linux)
   - Docker Compose v2.0+

2. **NVIDIA GPU 支持**
   - NVIDIA 显卡 (支持 CUDA 12.4)
   - NVIDIA 驱动程序
   - NVIDIA Container Toolkit

3. **数字人模型文件**
   - 下载模型文件并放到 `data/avatars/` 目录
   - 下载链接: https://pan.baidu.com/s/1lAkKh-HFeDNZFlU3XIKKZw (提取码: 3hxq)

## 快速开始

### 1. 准备配置文件

```bash
# 复制配置文件模板
cp ./conf/app_config.yaml.example ./conf/app_config.yaml

# 编辑配置文件，修改以下内容:
# - avatar_id: 你的数字人模型目录名
# - llm_type: "coze" 或 "openai"
# - 对应的 API 密钥和配置
vim ./conf/app_config.yaml
```

### 2. 准备模型文件

```bash
# 确保数字人模型已放置在正确位置
ls -la ./data/avatars/

# 可选: 下载 vosk 模型到 models 目录 (如果还没下载)
# wget -O ./models/vosk-model-cn-0.22.zip https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
```

### 3. 构建镜像

```bash
# 方式 1: 使用 docker-compose 构建
docker-compose build

# 方式 2: 使用 docker 直接构建
docker build -t livetalkingv15:latest .
```

### 4. 启动服务

```bash
# 启动服务 (后台运行)
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看服务状态
docker-compose ps
```

### 5. 访问服务

打开浏览器访问: `https://your-ip:8010`

**注意**: 
- 推荐使用 Firefox 浏览器
- 首次访问会有 SSL 证书警告，点击"高级" -> "继续访问"即可

## 常用命令

```bash
# 停止服务
docker-compose stop

# 启动服务
docker-compose start

# 重启服务
docker-compose restart

# 停止并删除容器
docker-compose down

# 停止并删除容器和数据卷
docker-compose down -v

# 查看日志
docker-compose logs -f livetalking

# 进入容器
docker-compose exec livetalking bash

# 重新构建并启动
docker-compose up -d --build
```

## 配置说明

### 端口映射

默认映射 `8010:8010`，如需修改宿主机端口:

```yaml
ports:
  - "9000:8010"  # 将宿主机 9000 端口映射到容器 8010 端口
```

### 数据卷挂载

**必需挂载**:
- `./data/avatars:/app/data/avatars` - 数字人模型目录

**可选挂载**:
- `./conf/app_config.yaml:/app/conf/app_config.yaml` - 配置文件
- `./ssl:/app/ssl` - 自定义 SSL 证书
- `./models:/app/models` - 模型持久化 (避免重复下载)

### GPU 配置

如果有多个 GPU，可以指定使用哪个:

```yaml
environment:
  - NVIDIA_VISIBLE_DEVICES=0  # 使用第一个 GPU
  # 或
  - NVIDIA_VISIBLE_DEVICES=0,1  # 使用前两个 GPU
```

### 代理配置

如果需要使用代理下载模型:

```yaml
build:
  args:
    http_proxy: http://your-proxy:port
    https_proxy: http://your-proxy:port
```

## 故障排查

### 1. GPU 不可用

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu20.04 nvidia-smi

# 安装 NVIDIA Container Toolkit (如果未安装)
# Ubuntu/Debian:
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 2. 端口被占用

```bash
# 检查端口占用
netstat -ano | findstr :8010  # Windows
lsof -i :8010                 # Linux/Mac

# 修改 docker-compose.yaml 中的端口映射
```

### 3. 模型下载失败

```bash
# 进入容器手动下载
docker-compose exec livetalking bash
cd /app
bash ./scripts/download_musetalk_weights.sh
```

### 4. 配置文件错误

```bash
# 检查配置文件格式
docker-compose exec livetalking cat /app/conf/app_config.yaml

# 重新复制配置文件
docker-compose restart
```

### 5. 查看详细日志

```bash
# 查看容器日志
docker-compose logs -f --tail=100 livetalking

# 进入容器查看应用日志
docker-compose exec livetalking bash
tail -f /app/logs/*.log  # 如果有日志文件
```

## 性能优化

### 1. 使用本地模型缓存

```yaml
volumes:
  - ./models:/app/models  # 持久化模型文件
```

### 2. 调整批处理大小

编辑 `conf/app_config.yaml`:

```yaml
server:
  batch_size: 25  # 根据 GPU 显存调整
```

### 3. 限制容器资源

```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 8G
```

## 更新升级

```bash
# 1. 停止服务
docker-compose down

# 2. 拉取最新代码
git pull

# 3. 重新构建镜像
docker-compose build --no-cache

# 4. 启动服务
docker-compose up -d
```

## 备份与恢复

### 备份

```bash
# 备份配置和数据
tar -czf livetalking-backup.tar.gz \
  conf/app_config.yaml \
  data/avatars/ \
  data/custom_config.json \
  ssl/
```

### 恢复

```bash
# 解压备份
tar -xzf livetalking-backup.tar.gz

# 重启服务
docker-compose restart
```

## 生产环境建议

1. **使用自定义 SSL 证书**: 替换 `ssl/` 目录下的证书文件
2. **配置反向代理**: 使用 Nginx/Traefik 作为前端代理
3. **启用日志轮转**: 配置 Docker 日志驱动
4. **监控和告警**: 集成 Prometheus + Grafana
5. **定期备份**: 备份配置文件和数字人模型
6. **资源限制**: 设置合理的 CPU 和内存限制

## 常见问题

**Q: 为什么推荐 Firefox 而不是 Chrome?**  
A: Chrome 对 WebRTC 的连接速度较慢，Firefox 表现更好。

**Q: 如何切换数字人模型?**  
A: 修改 `conf/app_config.yaml` 中的 `avatar_id`，然后重启容器。

**Q: 可以在 CPU 上运行吗?**  
A: 理论上可以，但性能会非常差，强烈建议使用 GPU。

**Q: 如何使用多个数字人?**  
A: 将多个模型放到 `data/avatars/` 目录，通过配置文件切换。

## 技术支持

- 原项目: https://gitee.com/lipku/LiveTalking
- 本项目: https://gitee.com/brucezhao/LiveTalking-v15
- 前端项目: https://gitee.com/brucezhao/livetalkingv15-webui
