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

import math
import torch
import numpy as np

#from .utils import *
import subprocess
import os
import time
import torch.nn.functional as F
import cv2
import glob
import pickle
import copy

import queue
from queue import Queue
from threading import Thread, Event
import torch.multiprocessing as mp

from musetalk.utils.utils import get_file_type,get_video_fps,datagen
#from musetalk.utils.preprocessing import get_landmark_and_bbox,read_imgs,coord_placeholder
from musetalk.utils.blending import get_image,get_image_prepare_material,get_image_blending
from musetalk.utils.utils import load_all_model,load_diffusion_model,load_audio_model
from musetalk.whisper.audio2feature import Audio2Feature

from museasr import MuseASR
import asyncio
from av import AudioFrame, VideoFrame
from basereal import BaseReal

from tqdm import tqdm
from logger import logger

def get_device():
    """获取可用的计算设备"""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    else:
        return torch.device("cpu")

def load_model(version):
    """加载模型权重"""
    audio_processor, vae, unet, pe = load_all_model(version)
    device = get_device()
    timesteps = torch.tensor([0], device=device)
    pe = pe.half()
    vae.vae = vae.vae.half()
    unet.model = unet.model.half()
    return vae, unet, pe, timesteps, audio_processor

def load_avatar(avatar_id):
    """加载角色资源"""
    avatar_path = f"./data/avatars/{avatar_id}"
    logger.info(f"Loading avatar from: {avatar_path}")
    paths = {
        "full_imgs": f"{avatar_path}/full_imgs",
        "coords": f"{avatar_path}/coords.pkl",
        "latents": f"{avatar_path}/latents.pt",
        "video_output": f"{avatar_path}/vid_output/",
        "mask": f"{avatar_path}/mask",
        "mask_coords": f"{avatar_path}/mask_coords.pkl",
        "avatar_info": f"{avatar_path}/avator_info.json"
    }

    try:
        input_latent_list_cycle = torch.load(paths["latents"])
        with open(paths["coords"], 'rb') as f:
            coord_list_cycle = pickle.load(f)
        input_img_list = sorted(
            glob.glob(os.path.join(paths["full_imgs"], '*.[jpJP][pnPN]*[gG]')),
            key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
        )
        frame_list_cycle = read_imgs(input_img_list)

        with open(paths["mask_coords"], 'rb') as f:
            mask_coords_list_cycle = pickle.load(f)
        input_mask_list = sorted(
            glob.glob(os.path.join(paths["mask"], '*.[jpJP][pnPN]*[gG]')),
            key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
        )
        mask_list_cycle = read_imgs(input_mask_list)

        return frame_list_cycle, mask_list_cycle, coord_list_cycle, mask_coords_list_cycle, input_latent_list_cycle
    except Exception as e:
        logger.error(f"Error loading avatar {avatar_id}: {e}")
        raise

@torch.no_grad()
def warm_up(batch_size, model):
    """预热模型"""
    logger.info('warmup model...')
    vae, unet, pe, timesteps, audio_processor = model
    device = unet.device

    whisper_batch = np.ones((batch_size, 50, 384), dtype=np.uint8)
    latent_batch = torch.ones(batch_size, 8, 32, 32, device=device)

    audio_feature_batch = torch.from_numpy(whisper_batch).to(device=device, dtype=unet.model.dtype)
    audio_feature_batch = pe(audio_feature_batch)
    latent_batch = latent_batch.to(dtype=unet.model.dtype)

    pred_latents = unet.model(latent_batch, timesteps, encoder_hidden_states=audio_feature_batch).sample
    vae.decode_latents(pred_latents)

def read_imgs(img_list):
    """读取图像列表"""
    if not img_list:
        return []
    logger.info('reading images...')
    return [cv2.imread(img_path) for img_path in tqdm(img_list)]

def mirror_index(size, index):
    """计算镜像索引"""
    turn = index // size
    res = index % size
    return res if turn % 2 == 0 else size - res - 1

@torch.no_grad()
def inference(render_event, batch_size, input_latent_list_cycle, audio_feat_queue, audio_out_queue, res_frame_queue,
              vae, unet, pe, timesteps):
    """推理函数"""
    length = len(input_latent_list_cycle)
    index = 0
    count = 0
    counttime = 0
    logger.info('start inference')

    while render_event.is_set():
        starttime = time.perf_counter()
        try:
            whisper_chunks = audio_feat_queue.get(block=True, timeout=1)
        except queue.Empty:
            continue

        is_all_silence = True
        audio_frames = []
        for _ in range(batch_size * 2):
            frame, frame_type, eventpoint = audio_out_queue.get()
            audio_frames.append((frame, frame_type, eventpoint))
            if frame_type == 0:
                is_all_silence = False

        if is_all_silence:
            for i in range(batch_size):
                res_frame_queue.put((None, mirror_index(length, index), audio_frames[i*2:i*2+2]))
                index += 1
        else:
            t = time.perf_counter()
            whisper_batch = np.stack(whisper_chunks)
            latent_batch = torch.cat([
                input_latent_list_cycle[mirror_index(length, index + i)]
                for i in range(batch_size)
            ], dim=0)

            audio_feature_batch = torch.from_numpy(whisper_batch).to(
                device=unet.device, dtype=unet.model.dtype
            )
            audio_feature_batch = pe(audio_feature_batch)
            latent_batch = latent_batch.to(dtype=unet.model.dtype)

            pred_latents = unet.model(latent_batch, timesteps, encoder_hidden_states=audio_feature_batch).sample
            recon = vae.decode_latents(pred_latents)

            counttime += (time.perf_counter() - t)
            count += batch_size
            if count >= 100:
                logger.info(f"------actual avg infer fps:{count/counttime:.4f}")
                count = 0
                counttime = 0

            for i, res_frame in enumerate(recon):
                res_frame_queue.put((res_frame, mirror_index(length, index), audio_frames[i*2:i*2+2]))
                index += 1

    logger.info('musereal inference processor stop')

class MuseReal(BaseReal):
    def __init__(self, opt, model, avatar):
        """初始化 MuseReal 类"""
        super().__init__(opt)
        self.fps = opt.fps
        self.batch_size = opt.batch_size
        self.idx = 0
        self.res_frame_queue = mp.Queue(self.batch_size * 2)

        self.vae, self.unet, self.pe, self.timesteps, self.audio_processor = model
        self.frame_list_cycle, self.mask_list_cycle, self.coord_list_cycle, self.mask_coords_list_cycle, self.input_latent_list_cycle = avatar

        self.asr = MuseASR(opt, self, self.audio_processor)
        self.asr.warm_up()
        self.render_event = mp.Event()

    def __del__(self):
        """析构函数"""
        logger.info(f'musereal({self.sessionid}) delete')

    def mirror_index(self, index):
        """计算镜像索引"""
        size = len(self.coord_list_cycle)
        return mirror_index(size, index)

    def warm_up(self):
        """预热模型"""
        self.asr.run_step()
        whisper_chunks = self.asr.get_next_feat()
        whisper_batch = np.stack(whisper_chunks)
        latent_batch = torch.cat([
            self.input_latent_list_cycle[self.mirror_index(self.idx + i)]
            for i in range(self.batch_size)
        ], dim=0)

        logger.info('infer=======')
        audio_feature_batch = torch.from_numpy(whisper_batch).to(
            device=self.unet.device, dtype=self.unet.model.dtype
        )
        audio_feature_batch = self.pe(audio_feature_batch)
        latent_batch = latent_batch.to(dtype=self.unet.model.dtype)

        pred_latents = self.unet.model(latent_batch, self.timesteps, encoder_hidden_states=audio_feature_batch).sample
        self.vae.decode_latents(pred_latents)

    def paste_back_frame(self, pred_frame, idx: int):
        """将预测帧粘贴回原始帧"""
        # 安全地访问列表，防止索引越界或NoneType错误
        if (self.coord_list_cycle is None or self.frame_list_cycle is None or 
            self.mask_list_cycle is None or self.mask_coords_list_cycle is None or
            idx >= len(self.coord_list_cycle) or idx >= len(self.frame_list_cycle) or
            idx >= len(self.mask_list_cycle) or idx >= len(self.mask_coords_list_cycle)):
            logger.warning(f"List is None or index out of range, skipping frame for session {getattr(self, 'sessionid', 'unknown')}")
            # 返回一个空的黑色帧作为备选方案
            height = getattr(self, 'height', 720)
            width = getattr(self, 'width', 1280)
            return np.zeros((height, width, 3), dtype=np.uint8)
            
        bbox = self.coord_list_cycle[idx]
        ori_frame = copy.deepcopy(self.frame_list_cycle[idx])
        x1, y1, x2, y2 = bbox

        res_frame = cv2.resize(pred_frame.astype(np.uint8), (x2 - x1, y2 - y1))
        mask = self.mask_list_cycle[idx]
        mask_crop_box = self.mask_coords_list_cycle[idx]

        combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
        return combine_frame

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        """渲染函数"""
        self.tts.render(quit_event)
        self.init_customindex()

        process_thread = Thread(target=self.process_frames, args=(quit_event, loop, audio_track, video_track))
        process_thread.start()

        self.render_event.set()
        Thread(target=inference, args=(
            self.render_event, self.batch_size, self.input_latent_list_cycle,
            self.asr.feat_queue, self.asr.output_queue, self.res_frame_queue,
            self.vae, self.unet, self.pe, self.timesteps
        )).start()

        count = 0
        totaltime = 0
        _starttime = time.perf_counter()

        while not quit_event.is_set():
            t = time.perf_counter()
            self.asr.run_step()

            if video_track and video_track._queue.qsize() >= 1.5 * self.batch_size:
                sleep_time = 0.04 * video_track._queue.qsize() * 0.8
                logger.debug('sleep qsize=%d, sleep_time=%.2f', video_track._queue.qsize(), sleep_time)
                time.sleep(sleep_time)

        self.render_event.clear()
        logger.info('musereal thread stop')