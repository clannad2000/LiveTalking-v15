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
#import gevent
#from gevent import pywsgi
#from geventwebsocket.handler import WebSocketHandler
import re
import numpy as np
from threading import Thread, Event
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
import argparse
import random
import shutil
import asyncio
import torch
from typing import Dict
from logger import logger
from vosk import Model
import tempfile
import ssl

app = Flask(__name__)
#sockets = Sockets(app)
nerfreals: Dict[int, BaseReal] = {}  # sessionid:BaseReal
opt = None
model = None
avatar = None

pcs = set()

vosk_model = Model("../voice-ai-persion/vosk-model-cn-0.22")

def randN(N) -> int:
    """生成长度为 N 的随机数"""
    min_val = 10 ** (N - 1)
    max_val = 10 ** N - 1
    return random.randint(min_val, max_val)

def build_nerfreal(sessionid: int) -> BaseReal:
    opt.sessionid = sessionid
    model_map = {
        'wav2lip': ('lipreal', 'LipReal'),
        'musetalk': ('musereal', 'MuseReal'),
        'musetalkv15': ('musereal', 'MuseReal'),
        'ultralight': ('lightreal', 'LightReal')
    }
    module_name, class_name = model_map.get(opt.model, (None, None))
    if module_name and class_name:
        module = __import__(module_name, fromlist=[class_name])
        nerfreal_class = getattr(module, class_name)
        return nerfreal_class(opt, model, avatar)
    raise ValueError(f"Unsupported model type: {opt.model}")

async def offer(request):
    """建立WebRTC连接
    ---
    tags:
    - WebRTC
    summary: 建立WebRTC连接并创建会话
    description: 客户端发送WebRTC offer以建立连接，服务器创建新会话并返回answer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              sdp: {type: string, description: WebRTC offer SDP}
              type: {type: string, description: WebRTC offer类型}
    responses:
      200:
        description: 成功建立连接
        content:
          application/json:
            schema:
              type: object
              properties:
                sdp: {type: string, description: WebRTC answer SDP}
                type: {type: string, description: WebRTC answer类型}
                sessionid: {type: integer, description: 会话ID}
      400:
        description: 已达到最大会话数
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
      500:
        description: 服务器内部错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        if len(nerfreals) >= opt.max_session:
            logger.info('reach max session')
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Reach max session"}),
                status=400
            )

        sessionid = randN(6)
        logger.info('Creating session with sessionid=%d', sessionid)
        nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)
        nerfreals[sessionid] = nerfreal
        logger.info('Session created with sessionid=%d', sessionid)

        ice_server1 = RTCIceServer(urls='stun:stun.miwifi.com:3478')
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[ice_server1]))
        pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s" % pc.connectionState)
            if pc.connectionState == "failed":
                await pc.close()
                pcs.discard(pc)
            if pc.connectionState == "closed":
                pcs.discard(pc)
                if sessionid in nerfreals:
                    logger.info('Deleting session with sessionid=%d', sessionid)
                    del nerfreals[sessionid]
                else:
                    logger.warning('Session with sessionid=%d not found when trying to delete', sessionid)

        player = HumanPlayer(nerfreals[sessionid])
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

async def process_audio(audiofile):
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

        wave = SaveWave(vosk_model, wav_file_path)
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

async def human(request):
    """处理人类交互
    ---
    tags:
    - 交互
    summary: 处理人类文本或音频输入
    description: 接收人类文本消息或音频文件，进行处理并返回结果
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
              type: {type: string, description: 交互类型，可选值为'echo'或'chat'}
              text: {type: string, description: 文本内容}
              interrupt: {type: boolean, description: 是否中断当前对话}
        multipart/form-data:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
              audio: {type: string, format: binary, description: 音频文件}
              interrupt: {type: boolean, description: 是否中断当前对话}
    responses:
      200:
        description: 处理成功
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 返回码，0表示成功}
                data: {type: string, description: 识别的文本内容或状态信息}
                llm_result: {type: string, description: LLM模型返回的结果}
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        content_type = request.headers.get('Content-Type', '')
        logger.info(f"Received request with Content-Type: {content_type}")
        logger.info("Request headers:")
        for header, value in request.headers.items():
            logger.info(f"{header}: {value}")

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
        if sessionid in nerfreals and params.get('interrupt'):
            nerfreals[sessionid].flush_talk()

        chatText = None
        llm_result = None
        if content_type == 'json':
            if params['type'] == 'echo':
                nerfreals[sessionid].put_msg_txt(params['text'])
            elif params['type'] == 'chat':
                chatText = params['text']
                llm_result = await asyncio.get_event_loop().run_in_executor(None, llm_response, chatText, nerfreals[sessionid], "coze")
        elif content_type == 'form':
            audiofile = params.get('audio')
            if audiofile:
                chatText = await process_audio(audiofile)
                if len(chatText) < 3:
                    return web.Response(
                        content_type="application/json",
                        text=json.dumps({"code": -1, "data": "Recognized text is too short"}),
                        status=400
                    )
                llm_result = await asyncio.get_event_loop().run_in_executor(None, llm_response, chatText, nerfreals[sessionid], "coze")

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

async def humanaudio(request):
    """处理人类音频
    ---
    tags:
    - 音频
    summary: 直接处理人类音频文件
    description: 接收音频文件并直接传递给数字人系统，不进行语音识别
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
              file: {type: string, format: binary, description: 音频文件}
    responses:
      200:
        description: 处理成功
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 返回码，0表示成功}
                msg: {type: string, description: 状态消息}
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                msg: {type: string, description: 错误消息}
                data: {type: string, description: 错误详情}
    """
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filebytes = fileobj.file.read()
        nerfreals[sessionid].put_audio_file(filebytes)

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

async def set_audiotype(request):
    """设置音频类型
    ---
    tags:
    - 配置
    summary: 设置数字人的音频类型和自定义状态
    description: 设置数字人的音频类型和是否重新初始化
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
              audiotype: {type: string, description: 音频类型}
              reinit: {type: boolean, description: 是否重新初始化}
    responses:
      200:
        description: 设置成功
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 返回码，0表示成功}
                data: {type: string, description: 状态消息}
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        nerfreals[sessionid].set_custom_state(params['audiotype'], params['reinit'])

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

async def record(request):
    """录制控制
    ---
    tags:
    - 录制
    summary: 控制数字人会话的录制功能
    description: 开始或停止数字人会话的录制
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
              type: {type: string, description: 录制类型，可选值为'start_record'或'end_record'}
    responses:
      200:
        description: 操作成功
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 返回码，0表示成功}
                data: {type: string, description: 状态消息}
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        if params['type'] == 'start_record':
            nerfreals[sessionid].start_recording()
        elif params['type'] == 'end_record':
            nerfreals[sessionid].stop_recording()
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

async def is_speaking(request):
    """检测说话状态
    ---
    tags:
    - 状态
    summary: 检查数字人是否正在说话
    description: 获取数字人当前是否处于说话状态
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              sessionid: {type: integer, description: 会话ID}
    responses:
      200:
        description: 查询成功
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 返回码，0表示成功}
                data: {type: boolean, description: 数字人是否正在说话}
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        speaking = nerfreals[sessionid].is_speaking()
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

async def download_recording(request):
    """下载录制视频
    ---
    tags:
    - 录制
    summary: 下载数字人会话的录制视频
    description: 根据会话ID下载对应的录制视频文件
    parameters:
      - name: sessionid
        in: query
        required: true
        description: 会话ID
        schema:
          type: integer
    responses:
      200:
        description: 成功返回视频文件
        content:
          video/mp4:
            schema:
              type: string
              format: binary
      400:
        description: 请求错误
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
      404:
        description: 视频文件不存在
        content:
          application/json:
            schema:
              type: object
              properties:
                code: {type: integer, description: 错误代码}
                data: {type: string, description: 错误信息}
    """
    try:
        # 获取查询参数中的sessionid
        sessionid = request.query.get('sessionid')
        if not sessionid:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Missing sessionid parameter"}),
                status=400
            )
        
        # 构建文件路径
        filename = f"{sessionid}_record.mp4"
        filepath = os.path.join("data", filename)
        
        # 检查文件是否存在
        if not os.path.exists(filepath):
            logger.error(f"Video file not found: {filepath}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "data": "Video file not found"}),
                status=404
            )
        
        # 设置响应头并发送文件
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

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.error(f'Error: {e}')
        return None

async def run(push_url, sessionid):
    nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)
    nerfreals[sessionid] = nerfreal

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    player = HumanPlayer(nerfreals[sessionid])
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    if answer:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type='answer'))

if __name__ == '__main__':
    mp.set_start_method('spawn')
    parser = argparse.ArgumentParser()

    # audio FPS
    parser.add_argument('--fps', type=int, default=50, help="audio fps,must be 50")
    # sliding window left-middle-right length (unit: 20ms)
    parser.add_argument('-l', type=int, default=10)
    parser.add_argument('-m', type=int, default=8)
    parser.add_argument('-r', type=int, default=10)

    parser.add_argument('--W', type=int, default=450, help="GUI width")
    parser.add_argument('--H', type=int, default=450, help="GUI height")

    # musetalk opt
    parser.add_argument('--avatar_id', type=str, default='avator_1', help="define which avatar in data/avatars")
    parser.add_argument('--bbox_shift', type=int, default=0)
    parser.add_argument('--batch_size', type=int, default=25, help="infer batch")

    parser.add_argument('--customvideo_config', type=str, default='', help="custom action json")

    parser.add_argument('--tts', type=str, default='edgetts', help="tts service type")  # xtts gpt-sovits cosyvoice
    parser.add_argument('--REF_FILE', type=str, default="zh-CN-XiaoyiNeural")
    parser.add_argument('--REF_TEXT', type=str, default=None)
    parser.add_argument('--TTS_SERVER', type=str, default='http://127.0.0.1:9880')  # http://localhost:9000
    # parser.add_argument('--CHARACTER', type=str, default='test')
    # parser.add_argument('--EMOTION', type=str, default='default')

    parser.add_argument('--model', type=str, default='musetalk')  # musetalk wav2lip ultralight

    parser.add_argument('--transport', type=str, default='rtcpush')  # webrtc rtcpush virtualcam
    parser.add_argument('--push_url', type=str, default='http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream')  # rtmp://localhost/live/livestream

    parser.add_argument('--max_session', type=int, default=3)  # multi session count
    parser.add_argument('--listenport', type=int, default=8010, help="web listen port")
    parser.add_argument('--ssl_cert', type=str, default='', help="Path to SSL certificate file")
    parser.add_argument('--ssl_key', type=str, default='', help="Path to SSL private key file")

    opt = parser.parse_args()
    opt.customopt = []
    if opt.customvideo_config != '':
        with open(opt.customvideo_config, 'r') as file:
            opt.customopt = json.load(file)

    model_load_info = {
        'musetalk': (1.0, 0),
        'musetalkv15': (1.5, 0),
        'wav2lip': ("./models/wav2lip.pth", 256),
        'ultralight': (opt, 160)
    }

    if opt.model in model_load_info:
        from_module = 'musereal' if 'musetalk' in opt.model else \
                      'lipreal' if opt.model == 'wav2lip' else 'lightreal'
        module = __import__(from_module, fromlist=['load_model', 'load_avatar', 'warm_up'])
        load_model = module.load_model
        load_avatar = module.load_avatar
        warm_up = module.warm_up

        load_param, warm_up_param = model_load_info[opt.model]
        logger.info(opt)
        model = load_model(load_param)
        avatar = load_avatar(opt.avatar_id)
        if warm_up_param:
            warm_up(opt.batch_size, model if opt.model != 'ultralight' else avatar, warm_up_param)
        else:
            warm_up(opt.batch_size, model)

    if opt.transport == 'virtualcam':
        thread_quit = Event()
        nerfreals[0] = build_nerfreal(0)
        rendthrd = Thread(target=nerfreals[0].render, args=(thread_quit,))
        rendthrd.start()

    appasync = web.Application(client_max_size=1024**2*100)
    appasync.on_shutdown.append(on_shutdown)
    
    # 配置Swagger文档
    setup_swagger(
        appasync,
        swagger_from_file='./conf/swagger_fixed.yaml', 
        swagger_url='/api/docs', 
        title='API doc'
    )
    
    # API路由
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/humanaudio", humanaudio)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/record", record)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_get("/download_recording", download_recording)  # 修改为GET方法
    appasync.router.add_static('/', path='web')

    # 为根路径添加处理程序，重定向到dashboard.html
    async def handle_root(request):
        logger.info(f"Root request from IP: {request.remote}")
        return web.HTTPFound('/dashboard.html')
    appasync.router.add_get('/', handle_root)

    # Configure default CORS settings with more explicit method allowances
    cors = aiohttp_cors.setup(appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"]
        )
    })
    # Configure CORS on all routes.
    for route in list(appasync.router.routes()):
        logger.info(f"Adding CORS to route: {route}")
        cors.add(route)

    pagename = 'dashboard.html'
    if opt.transport == 'rtmp':
        pagename = 'echoapi.html'
    elif opt.transport == 'rtcpush':
        pagename = 'rtcpushapi.html'
    
    # 根据是否提供SSL证书决定使用HTTP还是HTTPS
    if opt.ssl_cert and opt.ssl_key:
        logger.info('start https server; https://<serverip>:'+str(opt.listenport)+'/'+pagename)
        logger.info('如果使用webrtc，推荐访问webrtc集成前端: https://<serverip>:'+str(opt.listenport)+'/dashboard.html')
    else:
        logger.info('start http server; http://<serverip>:'+str(opt.listenport)+'/'+pagename)
        logger.info('如果使用webrtc，推荐访问webrtc集成前端: http://<serverip>:'+str(opt.listenport)+'/dashboard.html')

    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        
        # 配置SSL上下文（如果提供了证书和密钥）
        if opt.ssl_cert and opt.ssl_key:
            try:
                # 确保证书和密钥文件存在
                if not os.path.exists(opt.ssl_cert):
                    logger.error(f"SSL certificate file not found: {opt.ssl_cert}")
                    return
                if not os.path.exists(opt.ssl_key):
                    logger.error(f"SSL private key file not found: {opt.ssl_key}")
                    return
                
                # 检查文件权限
                cert_stat = os.stat(opt.ssl_cert)
                key_stat = os.stat(opt.ssl_key)
                logger.info(f"Certificate file permissions: {oct(cert_stat.st_mode)[-3:]}")
                logger.info(f"Private key file permissions: {oct(key_stat.st_mode)[-3:]}")
                
                # 创建SSL上下文
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ssl_context.load_cert_chain(certfile=opt.ssl_cert, keyfile=opt.ssl_key)
                logger.info(f"Successfully loaded SSL certificate from {opt.ssl_cert}")
                
                # 设置SSL上下文选项
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Use TCPSite with ssl_context parameter
                site = web.TCPSite(runner, '0.0.0.0', opt.listenport, ssl_context=ssl_context)
                logger.info(f"Starting HTTPS server on port {opt.listenport}")
            except Exception as e:
                logger.error(f"Failed to set up SSL context: {str(e)}")
                # 回退到HTTP
                site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
                logger.info(f"Falling back to HTTP server on port {opt.listenport}")
        else:
            site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
            logger.info(f"Starting HTTP server on port {opt.listenport}")
            
        loop.run_until_complete(site.start())
        if opt.transport == 'rtcpush':
            for k in range(opt.max_session):
                push_url = opt.push_url
                if k != 0:
                    push_url = opt.push_url + str(k)
                loop.run_until_complete(run(push_url, k))
        loop.run_forever()

    run_server(web.AppRunner(appasync))

    #app.on_shutdown.append(on_shutdown)
    #app.router.add_post("/offer", offer)

    # print('start websocket server')
    # server = pywsgi.WSGIServer(('0.0.0.0', 8000), app, handler_class=WebSocketHandler)
    # server.serve_forever()