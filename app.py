###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#       http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

# server.py
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_sockets import Sockets
import base64
import json
import yaml
#import gevent
#from gevent import pywsgi
#from geventwebsocket.handler import WebSocketHandler
import re
import numpy as np
from threading import Thread, Event, Lock
#import multiprocessing
import torch.multiprocessing as mp

from aiohttp import web
import aiohttp
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration
from aiortc.rtcrtpsender import RTCRtpSender
from aiohttp_swagger import setup_swagger
from llm_coze import SaveWave
from webrtc import HumanPlayer
from basereal import BaseReal
from llm import llm_response
from pydub import AudioSegment
import os
import random
import shutil
import asyncio
import torch
from typing import Dict
from logger import logger
from vosk import Model
import tempfile
import ssl
import threading

app = Flask(__name__)

def randN(N) -> int:
    """生成长度为 N 的随机数"""
    min_val = 10 ** (N - 1)
    max_val = 10 ** N - 1
    return random.randint(min_val, max_val)

# 创建应用上下文类来封装全局变量
class AppContext:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls):
        """获取AppContext单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        # 确保单例模式，防止重复初始化
        if hasattr(self, '_initialized'):
            return
            
        self.nerfreals: Dict[int, BaseReal] = {}  # sessionid:BaseReal
        self.opt = None
        self.model = None
        self.avatar = None  # 全局avatar变量，供config_manager访问
        self.pcs = set()
        self.vosk_model = None  # 将在main函数中初始化
        self.appasync = None
        self.flask_app = app  # Flask应用实例
        
        self._initialized = True
    
    def reset(self):
        """重置所有状态"""
        self.nerfreals.clear()
        self.opt = None
        self.model = None
        self.avatar = None
        self.pcs.clear()
        self.vosk_model = None
        self.appasync = None
        self.flask_app = app


# 修改build_nerfreal函数，使用应用上下文
def build_nerfreal(sessionid: int, context: AppContext) -> BaseReal:
    context.opt.sessionid = sessionid
    model_map = {
        'wav2lip': ('lipreal', 'LipReal'),
        'musetalk': ('musereal', 'MuseReal'),
        'musetalkv15': ('musereal', 'MuseReal'),
        'ultralight': ('lightreal', 'LightReal')
    }
    module_name, class_name = model_map.get(context.opt.model, (None, None))
    if module_name and class_name:
        module = __import__(module_name, fromlist=[class_name])
        nerfreal_class = getattr(module, class_name)
        return nerfreal_class(context.opt, context.model, context.avatar)
    raise ValueError(f"Unsupported model type: {context.opt.model}")

# 修改offer函数，使用应用上下文
async def offer(context: AppContext, request):
    """建立WebRTC连接"""
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        if len(context.nerfreals) >= context.opt.max_session:
            logger.info('reach max session')
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Reach max session"}),
                status=400
            )

        sessionid = randN(6)
        logger.info('Creating session with sessionid=%d', sessionid)
        nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, context)
        context.nerfreals[sessionid] = nerfreal
        logger.info('Session created with sessionid=%d', sessionid)

        ice_server1 = RTCIceServer(urls='stun:stun.miwifi.com:3478')
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[ice_server1]))
        context.pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s" % pc.connectionState)
            if pc.connectionState == "failed":
                await pc.close()
                context.pcs.discard(pc)
            if pc.connectionState == "closed":
                context.pcs.discard(pc)
                if sessionid in context.nerfreals:
                    logger.info('Deleting session with sessionid=%d', sessionid)
                    del context.nerfreals[sessionid]
                else:
                    logger.warning('Session with sessionid=%d not found when trying to delete', sessionid)

        player = HumanPlayer(context.nerfreals[sessionid])
        audio_sender = pc.addTrack(player.audio)
        video_sender = pc.addTrack(player.video)
        capabilities = RTCRtpSender.getCapabilities("video")
        preferences = [codec for codec in capabilities.codecs if codec.name in ("H264", "VP8", "rtx")]
        transceiver = pc.getTransceivers()[1]
        transceiver.setCodecPreferences(preferences)

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "sessionid": sessionid}
            ),
        )
    except Exception as e:
        logger.error(f"Error in offer: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in offer: {str(e)}"}),
            status=500
        )

# 修改process_audio函数，使用应用上下文
async def process_audio(audiofile, context: AppContext):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
        tmp_file.write(audiofile.file.read())
        tmp_file_path = tmp_file.name

    try:
        if os.path.getsize(tmp_file_path) == 0:
            raise ValueError("Audio file is empty")

        wav_file_path = tmp_file_path.replace('.tmp', '.wav')
        original_audio = AudioSegment.from_file(tmp_file_path)
        logger.info(f"Original audio info: channels={original_audio.channels}, frame_rate={original_audio.frame_rate}, sample_width={original_audio.sample_width}")

        audio = original_audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        audio.export(wav_file_path, format='wav')

        converted_audio = AudioSegment.from_file(wav_file_path)
        logger.info(f"Converted audio info: channels={converted_audio.channels}, frame_rate={converted_audio.frame_rate}, sample_width={converted_audio.sample_width}")

        wave = SaveWave(context.vosk_model, wav_file_path)
        text = wave.listen()
        logger.info(f"-------Recognized text: {text}")
        return text
    except Exception as e:
        logger.error(f"Error processing audio file: {e}")
        raise
    finally:
        try:
            os.remove(tmp_file_path)
        except FileNotFoundError:
            pass
        try:
            os.remove(wav_file_path)
        except FileNotFoundError:
            pass

# 修改human函数，使用应用上下文
async def human(context: AppContext, request):
    """处理人类交互"""
    try:
        content_type = request.headers.get('Content-Type', '')
        logger.info(f"Received request with Content-Type: {content_type}")

        params = {}
        if 'application/json' in content_type:
            params = await request.json()
            content_type = 'json'
        elif 'multipart/form-data' in content_type:
            form = await request.post()
            params = dict(form)
            content_type = 'form'
        else:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Unsupported Content-Type"}),
                status=400
            )

        sessionid = int(params.get('sessionid', 0))
        if sessionid in context.nerfreals and params.get('interrupt'):
            context.nerfreals[sessionid].flush_talk()

        chatText = None
        llm_result = None
        if content_type == 'json':
            if params['type'] == 'echo':
                context.nerfreals[sessionid].put_msg_txt(params['text'])
            elif params['type'] == 'chat':
                chatText = params['text']
                llm_result = await asyncio.get_event_loop().run_in_executor(None, llm_response, chatText, context.nerfreals[sessionid], context.opt.llm_type)
        elif content_type == 'form':
            audiofile = params.get('audio')
            if audiofile:
                chatText = await process_audio(audiofile, context)
                if len(chatText) < 3:
                    return web.Response(
                        content_type="application/json",
                        text=json.dumps({"code": -1, "data": "Recognized text is too short"}),
                        status=400
                    )
                llm_result = await asyncio.get_event_loop().run_in_executor(None, llm_response, chatText, context.nerfreals[sessionid], context.opt.llm_type)

        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": chatText, "llm_result": llm_result}) if chatText else json.dumps({"code": 0, "data": "ok", "llm_response": "None"})
        )
    except Exception as e:
        logger.error(f"Error in human: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in human: {str(e)}"}),
            status=400
        )

# 修改humanaudio函数，使用应用上下文
async def humanaudio(context: AppContext, request):
    """处理人类音频"""
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filebytes = fileobj.file.read()
        context.nerfreals[sessionid].put_audio_file(filebytes)

        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "msg": "ok"})
        )
    except Exception as e:
        logger.error(f"Error in humanaudio: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "err", "data": str(e)}),
            status=400
        )

# 修改set_audiotype函数，使用应用上下文
async def set_audiotype(context: AppContext, request):
    """设置音频类型"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        context.nerfreals[sessionid].set_custom_state(params['audiotype'], params['reinit'])

        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": "ok"})
        )
    except Exception as e:
        logger.error(f"Error in set_audiotype: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in set_audiotype: {str(e)}"}),
            status=400
        )

# 修改record函数，使用应用上下文
async def record(context: AppContext, request):
    """录制控制"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        if params['type'] == 'start_record':
            context.nerfreals[sessionid].start_recording()
        elif params['type'] == 'end_record':
            context.nerfreals[sessionid].stop_recording()
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": "ok"})
        )
    except Exception as e:
        logger.error(f"Error in record: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in record: {str(e)}"}),
            status=400
        )

# 修改is_speaking函数，使用应用上下文
async def is_speaking(context: AppContext, request):
    """检测说话状态"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        speaking = context.nerfreals[sessionid].is_speaking()
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": speaking})
        )
    except Exception as e:
        logger.error(f"Error in is_speaking: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in is_speaking: {str(e)}"}),
            status=400
        )

# 修改download_recording函数，使用应用上下文
async def download_recording(context: AppContext, request):
    """下载录制视频"""
    try:
        sessionid = request.query.get('sessionid')
        if not sessionid:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Missing sessionid parameter"}),
                status=400
            )

        filename = f"{sessionid}_record.mp4"
        filepath = os.path.join("data", filename)

        if not os.path.exists(filepath):
            logger.error(f"Video file not found: {filepath}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Video file not found"}),
                status=404
            )

        response = web.FileResponse(filepath)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'video/mp4'
        logger.info(f"Downloading video: {filepath}")
        return response
    except Exception as e:
        logger.error(f"Error in download_recording: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error downloading video: {str(e)}"}),
            status=500
        )

# 修改on_shutdown函数，使用应用上下文
async def on_shutdown(context: AppContext, app):
    coros = [pc.close() for pc in context.pcs]
    await asyncio.gather(*coros)
    context.pcs.clear()

# 修改run函数，使用应用上下文
async def run(context: AppContext):
    # 创建aiohttp应用
    context.appasync = web.Application(client_max_size=1024**2*100)
    
    # 注册配置管理的API路由
    from config_manager import ConfigManager
    config_manager = ConfigManager()
    config_manager.set_app_context(context)
    config_manager.register_routes(context.appasync)
    
    # 配置Swagger文档
    setup_swagger(
        context.appasync,
        swagger_from_file='./conf/swagger_fixed.yaml', 
        swagger_url='/api/docs', 
        title='API doc'
    )
    
    # 注册API路由
    context.appasync.router.add_post('/offer', lambda request: offer(context, request))
    context.appasync.router.add_post('/human', lambda request: human(context, request))
    context.appasync.router.add_post('/humanaudio', lambda request: humanaudio(context, request))
    context.appasync.router.add_post('/set_audiotype', lambda request: set_audiotype(context, request))
    context.appasync.router.add_post('/record', lambda request: record(context, request))
    context.appasync.router.add_post('/is_speaking', lambda request: is_speaking(context, request))
    context.appasync.router.add_get('/download_recording', lambda request: download_recording(context, request))
    context.appasync.router.add_static('/', path='web')
    
    # 为根路径添加处理程序，重定向到dashboard.html
    async def handle_root(request):
        logger.info(f"Root request from IP: {request.remote}")
        pagename = 'dashboard.html'
        if context.opt.transport == 'rtmp':
            pagename = 'echoapi.html'
        elif context.opt.transport == 'rtcpush':
            pagename = 'rtcpushapi.html'
        return web.HTTPFound(f'/{pagename}')
    
    context.appasync.router.add_get('/', handle_root)
    
    # Configure default CORS settings
    cors = aiohttp_cors.setup(context.appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"]
        )
    })
    
    # Configure CORS on all routes
    for route in list(context.appasync.router.routes()):
        logger.info(f"Adding CORS to route: {route}")
        cors.add(route)
    
    # 设置关闭回调
    context.appasync.on_shutdown.append(lambda app: on_shutdown(context, app))
    
    # 启动服务器
    runner = web.AppRunner(context.appasync)
    await runner.setup()
    
    # 配置SSL上下文（如果提供了证书和密钥）
    if context.opt.ssl_cert and context.opt.ssl_key:
        try:
            # 确保证书和密钥文件存在
            if not os.path.exists(context.opt.ssl_cert):
                logger.error(f"SSL certificate file not found: {context.opt.ssl_cert}")
                return
            if not os.path.exists(context.opt.ssl_key):
                logger.error(f"SSL private key file not found: {context.opt.ssl_key}")
                return
            
            # 检查文件权限
            cert_stat = os.stat(context.opt.ssl_cert)
            key_stat = os.stat(context.opt.ssl_key)
            logger.info(f"Certificate file permissions: {oct(cert_stat.st_mode)[-3:]}")
            logger.info(f"Private key file permissions: {oct(key_stat.st_mode)[-3:]}")
            
            # 创建SSL上下文
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=context.opt.ssl_cert, keyfile=context.opt.ssl_key)
            logger.info(f"Successfully loaded SSL certificate from {context.opt.ssl_cert}")
            
            # 设置SSL上下文选项
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Use TCPSite with ssl_context parameter
            site = web.TCPSite(runner, '0.0.0.0', context.opt.listenport, ssl_context=ssl_context)
            logger.info(f"Starting HTTPS server on port {context.opt.listenport}")
            logger.info(f'HTTPS server started: https://<serverip>:{context.opt.listenport}/dashboard.html')
        except Exception as e:
            logger.error(f"Failed to set up SSL context: {str(e)}")
            # 回退到HTTP
            site = web.TCPSite(runner, '0.0.0.0', context.opt.listenport)
            logger.info(f"Falling back to HTTP server on port {context.opt.listenport}")
            logger.info(f'HTTP server started: http://<serverip>:{context.opt.listenport}/dashboard.html')
    else:
        site = web.TCPSite(runner, '0.0.0.0', context.opt.listenport)
        logger.info(f"Starting HTTP server on port {context.opt.listenport}")
        logger.info(f'HTTP server started: http://<serverip>:{context.opt.listenport}/dashboard.html')
    
    await site.start()
    
    # RTCPush模式下启动推送
    if context.opt.transport == 'rtcpush':
        for k in range(context.opt.max_session):
            push_url = context.opt.push_url
            if k != 0:
                push_url = context.opt.push_url + str(k)
            await run_rtcpush_session(push_url, k, context)
    
    # 保持服务器运行
    logger.info("Server started successfully. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)  # 睡眠一小时
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        await runner.cleanup()

# 添加RTCPush运行函数
async def run_rtcpush(push_url, session_index, context: AppContext):
    """RTCPush模式运行函数"""
    logger.info(f"Starting RTCPush for session {session_index} to {push_url}")
    # 这里添加RTCPush的具体实现
    pass

async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.error(f'Error: {e}')
        return None

async def run_rtcpush_session(push_url, sessionid, context: AppContext):
    """RTCPush模式下运行单个会话"""
    nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, context)
    context.nerfreals[sessionid] = nerfreal

    pc = RTCPeerConnection()
    context.pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            context.pcs.discard(pc)

    player = HumanPlayer(context.nerfreals[sessionid])
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    if answer:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type='answer'))

# 修改main函数，使用应用上下文
def main():
    """主函数"""
    global app_context
    
    try:
        # 设置多进程启动方法
        mp.set_start_method('spawn')
        
        # 初始化应用上下文
        app_context = AppContext.get_instance()
        
        # 从YAML配置文件读取参数
        with open('conf/app_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # 创建opt对象，包含所有配置参数
        app_context.opt = type('Options', (), config['server'])()
        
        # 初始化customopt（如果有自定义视频配置）
        app_context.opt.customopt = []
        if hasattr(app_context.opt, 'customvideo_config') and app_context.opt.customvideo_config != '':
            try:
                with open(app_context.opt.customvideo_config, 'r') as file:
                    # 根据文件扩展名决定使用json还是yaml
                    if app_context.opt.customvideo_config.endswith('.yaml') or app_context.opt.customvideo_config.endswith('.yml'):
                        app_context.opt.customopt = yaml.safe_load(file)
                    else:
                        app_context.opt.customopt = json.load(file)
            except Exception as e:
                logger.error(f"Failed to load custom video config: {e}")
        
        # 模型加载信息映射
        model_load_info = {
            'musetalk': (1.0, 0),
            'musetalkv15': (1.5, 0),
            'wav2lip': ("models/wav2lip.pth", 256),
            'ultralight': (app_context.opt, 160)
        }
        
        # 根据配置的模型类型加载相应的模块和函数
        if app_context.opt.model in model_load_info:
            from_module = 'musereal' if 'musetalk' in app_context.opt.model else \
                         'lipreal' if app_context.opt.model == 'wav2lip' else 'lightreal'
            module = __import__(from_module, fromlist=['load_model', 'load_avatar', 'warm_up'])
            load_model = module.load_model
            load_avatar = module.load_avatar
            warm_up = module.warm_up

            load_param, warm_up_param = model_load_info[app_context.opt.model]
            logger.info(app_context.opt)
            app_context.model = load_model(load_param)
            # 更新全局avatar变量
            app_context.avatar = load_avatar(app_context.opt.avatar_id)
            if warm_up_param:
                warm_up(app_context.opt.batch_size, app_context.model if app_context.opt.model != 'ultralight' else app_context.avatar, warm_up_param)
            else:
                warm_up(app_context.opt.batch_size, app_context.model)
        
        # 初始化Vosk模型
        app_context.vosk_model = Model("../voice-ai-persion/vosk-model-cn-0.22")
        
        logger.info(f"Model loaded: {app_context.opt.model}")

        # virtualcam模式下启动渲染线程
        if app_context.opt.transport == 'virtualcam':
            thread_quit = Event()
            app_context.nerfreals[0] = build_nerfreal(0, app_context)
            rendthrd = Thread(target=app_context.nerfreals[0].render, args=(thread_quit,))
            rendthrd.start()

        # 启动服务
        logger.info("Starting server...")
        asyncio.run(run(app_context))
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

# 添加程序入口点
if __name__ == '__main__':
    main()