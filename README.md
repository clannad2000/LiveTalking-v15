# LiveTalking-v15

本工程在 [LiveTalking](https://gitee.com/lipku/LiveTalking) 的基础上进行开发，新增了多项实用功能并修复了若干已知问题。

## 主要特性
- 支持 MuseTalk v1.5 模型
- 修复麦克风无法使用的问题
- 新增本地语音识别功能（基于 Vosk）
- 集成 Coze 工作流，增强语言模型交互能力
- 支持对话记录功能
- 增加 HTTPS 支持，提供默认 SSL 证书
- 支持麦克风持续收音
- 前后端分离架构：前端使用 Vue，后端使用 Flask
- 支持运行时切换数字人模型和语言模型
- 配置管理从环境变量迁移至配置文件 `./conf/app_config.yaml`

## 部署指南

### 后端部署

#### 环境要求
- Python 3.10
- PyTorch 2.4
- CUDA 12.4

#### 安装依赖
```bash
conda install pytorch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 pytorch-cuda=12.4 -c pytorch -c nvidia
git clone https://gitee.com/brucezhao/LiveTalking-v15.git
git checkout -b front-back-separa origin/front-back-separa
cd LiveTalking-v15

apt install libasound-dev portaudio19-dev libportaudio2 libportaudiocpp0 libgl1
pip install -r requirements.txt

# 下载 MuseTalk v1.5 模型权重
./scripts/download_musetalk_weights.sh
# 下载 Whisper Tiny 模型权重
wget -O ./models/whisper/tiny.pt https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt
```

#### 配置本地语音识别模型
```bash
mkdir /root/voice-ai-persion
wget -O /root/voice-ai-persion/vosk-model-cn-0.22.zip https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
cd /root/voice-ai-persion
unzip vosk-model-cn-0.22.zip
```

#### 修改配置文件
```bash
cp ./conf/app_config.yaml.example ./conf/app_config.yaml
vim ./conf/app_config.yaml
```

#### 启动服务
```bash
python app.py
```

### 前端部署

#### 环境要求
- Node.js v20.5.0

#### 安装依赖
```bash
git clone https://gitee.com/brucezhao/livetalkingv15-webui.git
cd livetalkingv15-webui

npm install
```

#### 修改配置
修改 `vite.config.js` 中的 `backend` 为服务地址和端口号。

#### 启动前端服务
```bash
npm run dev
```

## 访问服务

使用火狐浏览器访问 `http://ip:3000`（不推荐使用谷歌浏览器）。由于使用了自签名证书，访问时会出现安全警告，请点击高级设置并确认继续访问。

## 使用说明

点击左上角图标可以修改配置，修改后需点击“保存”按钮生效。若修改了数字人模型，需断开当前连接后重新点击“开始连接”按钮。

点击“启用麦克风”按钮即可启用麦克风，实现与数字人的连续语音交互。