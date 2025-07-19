import os
import json
import wave
import pyaudio  
from cozepy import COZE_CN_BASE_URL
from cozepy import Coze, TokenAuth, Message, ChatStatus, MessageContentType  # noqa
from vosk import Model, KaldiRecognizer, SetLogLevel


# 从环境变量中获取 coze_api_token 和 workflow_id
coze_api_token = os.getenv('COZE_API_TOKEN')
if not coze_api_token:
    raise ValueError("COZE_API_TOKEN 环境变量未设置")

workflow_id = os.getenv('WORKFLOW_ID')
if not workflow_id:
    raise ValueError("WORKFLOW_ID 环境变量未设置")

coze_api_base = COZE_CN_BASE_URL

# 语音识别模块
import wave
import json
from vosk import Model, KaldiRecognizer


class SaveWave:
    def __init__(self, model, audio_file):
        self.model = model
        self.audio_file = audio_file
        try:
            self.wf = wave.open(audio_file, 'rb')
            # 打印音频文件信息
            print(f"Audio file info: nchannels={self.wf.getnchannels()}, sampwidth={self.wf.getsampwidth()}, framerate={self.wf.getframerate()}, nframes={self.wf.getnframes()}")
            self.rec = KaldiRecognizer(self.model, 16000)
        except Exception as e:
            print(f"Error opening audio file: {e}")
            raise

    def listen(self):
        text_parts = []
        chunk_size = 4096
        while True:
            data = self.wf.readframes(chunk_size)
            if len(data) == 0:
                print("No more data to read from the audio file.")
                break
            if self.rec.AcceptWaveform(data):
                result = self.rec.Result()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")
                if text:
                    text_parts.append(text)
        final_result = self.rec.FinalResult()
        final_result_dict = json.loads(final_result)
        text = final_result_dict.get("text", "")
        if text:
            text_parts.append(text)
        return " ".join(text_parts)

class CozeWorkflow:
    def __init__(self):
        # Initialize the Coze client with the provided token and base URL
        self.coze = Coze(auth=TokenAuth(token=coze_api_token), base_url=coze_api_base)
        
    def chat_with_coze(self, text):
        
        # Call the coze.workflows.runs.create method to create a workflow run. The create method
        # is a non-streaming chat and will return a WorkflowRunResult class.
        workflow = self.coze.workflows.runs.create(
            workflow_id=workflow_id,
            parameters={
                "input": text
            },
        )

        data = json.loads(workflow.data)

        return data['data']