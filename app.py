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

app = Flask(__name__)
#sockets = Sockets(app)
nerfreals: Dict[int, BaseReal] = {}  # sessionid:BaseReal
opt = None
model = None
avatar = None

pcs = set()

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

vosk_model = Model("/workspace/voice-ai-persion/vosk-model-cn-0.22")

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

        if content_type == 'json':
            if params['type'] == 'echo':
                nerfreals[sessionid].put_msg_txt(params['text'])
            elif params['type'] == 'chat':
                text = params['text']
                res = await asyncio.get_event_loop().run_in_executor(None, llm_response, text, nerfreals[sessionid], "coze")
        elif content_type == 'form':
            audiofile = params.get('audio')
            if audiofile:
                text = await process_audio(audiofile)
                res = await asyncio.get_event_loop().run_in_executor(None, llm_response, text, nerfreals[sessionid], "coze")

        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": "ok"})
        )
    except Exception as e:
        logger.error(f"Error in human: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in human: {str(e)}"}),
            status=400
        )

async def humanaudio(request):
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
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": nerfreals[sessionid].is_speaking()})
        )
    except Exception as e:
        logger.error(f"Error in is_speaking: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "data": f"Error in is_speaking: {str(e)}"}),
            status=400
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
    parser.add_argument('--batch_size', type=int, default=16, help="infer batch")

    parser.add_argument('--customvideo_config', type=str, default='', help="custom action json")

    parser.add_argument('--tts', type=str, default='edgetts', help="tts service type")  # xtts gpt-sovits cosyvoice
    parser.add_argument('--REF_FILE', type=str, default="zh-CN-YunxiNeural")
    parser.add_argument('--REF_TEXT', type=str, default=None)
    parser.add_argument('--TTS_SERVER', type=str, default='http://127.0.0.1:9880')  # http://localhost:9000
    # parser.add_argument('--CHARACTER', type=str, default='test')
    # parser.add_argument('--EMOTION', type=str, default='default')

    parser.add_argument('--model', type=str, default='musetalk')  # musetalk wav2lip ultralight

    parser.add_argument('--transport', type=str, default='rtcpush')  # webrtc rtcpush virtualcam
    parser.add_argument('--push_url', type=str, default='http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream')  # rtmp://localhost/live/livestream

    parser.add_argument('--max_session', type=int, default=1)  # multi session count
    parser.add_argument('--listenport', type=int, default=8010, help="web listen port")

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
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/humanaudio", humanaudio)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/record", record)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_static('/', path='web')

    # Configure default CORS settings.
    cors = aiohttp_cors.setup(appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    # Configure CORS on all routes.
    for route in list(appasync.router.routes()):
        cors.add(route)

    pagename = 'dashboard.html'
    if opt.transport == 'rtmp':
        pagename = 'echoapi.html'
    elif opt.transport == 'rtcpush':
        pagename = 'rtcpushapi.html'
    logger.info('start http server; http://<serverip>:'+str(opt.listenport)+'/'+pagename)
    logger.info('如果使用webrtc，推荐访问webrtc集成前端: http://<serverip>:'+str(opt.listenport)+'/dashboard.html')

    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
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
    
