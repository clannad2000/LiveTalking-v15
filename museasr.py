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

import time
import numpy as np
from queue import Queue
from baseasr import BaseASR
from musetalk.whisper.audio2feature import Audio2Feature
from logger import logger

class MuseASR(BaseASR):
    def __init__(self, opt, parent, audio_processor: Audio2Feature):
        super().__init__(opt, parent)
        self.audio_processor = audio_processor
        self.frames = []
        self.feat_queue = Queue()
        self.output_queue = Queue()

    def run_step(self):
        """执行一步音频特征提取操作"""
        start_time = time.perf_counter()  # 使用 perf_counter 获得更高精度计时

        try:
            # 收集音频帧
            for _ in range(self.batch_size * 2):
                audio_frame, frame_type, eventpoint = self.get_audio_frame()
                self.frames.append(audio_frame)
                self.output_queue.put((audio_frame, frame_type, eventpoint))

            # 检查帧长度是否足够
            stride_total = self.stride_left_size + self.stride_right_size
            if len(self.frames) <= stride_total:
                return

            # 拼接音频帧
            inputs = np.concatenate(self.frames)

            # 提取音频特征
            whisper_feature = self.audio_processor.audio2feat(inputs)

            # 分割特征为块
            whisper_chunks = self.audio_processor.feature2chunks(
                feature_array=whisper_feature,
                fps=self.fps / 2,
                batch_size=self.batch_size,
                start=self.stride_left_size / 2
            )

            # 将特征块放入队列
            self.feat_queue.put(whisper_chunks)

            # 丢弃旧的音频帧以节省内存
            self.frames = self.frames[-stride_total:]

            # 记录处理耗时
            process_time = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Processing audio costs {process_time:.2f}ms, inputs shape: {inputs.shape}, whisper_feature len: {len(whisper_feature)}")

        except Exception as e:
            logger.error(f"Error in run_step: {e}")