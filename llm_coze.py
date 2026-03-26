import os
import json
import wave
import yaml
from logger import logger
import pyaudio  
from cozepy import COZE_CN_BASE_URL
from cozepy import Coze, TokenAuth, Message, ChatStatus, MessageContentType  # noqa
from vosk import Model, KaldiRecognizer, SetLogLevel

# 读取配置文件
def read_config():
    config_path = "./conf/app_config.yaml"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Failed to read config file: {e}")
        # 不返回默认配置
        return {}

# 全局配置对象
config = read_config()

# 从配置文件获取参数
def get_coze_config():
    llm_config = config.get('llm', {}).get('coze', {})
    
    # 处理api_token，如果是环境变量格式则获取环境变量值
    api_token = llm_config.get('api_token', '')
    # 处理workflow_id，如果是环境变量格式则获取环境变量值
    workflow_id = llm_config.get('workflow_id', '')

    
    # 验证必要的配置参数
    if not api_token:
        raise ValueError("COZE_API_TOKEN 未配置")
    
    if not workflow_id:
        raise ValueError("WORKFLOW_ID 未配置")
    
    # 获取base_url
    base_url = llm_config.get('base_url', COZE_CN_BASE_URL)
    
    return api_token, workflow_id, base_url

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
        self.coze_api_token, self.workflow_id, self.coze_api_base = get_coze_config()
        self.coze = Coze(auth=TokenAuth(token=self.coze_api_token), base_url=self.coze_api_base)
        
    def chat_with_coze(self, text):
        
        # Call the coze.workflows.runs.create method to create a workflow run. The create method
        # is a non-streaming chat and will return a WorkflowRunResult class.
        workflow = self.coze.workflows.runs.create(
            workflow_id=self.workflow_id,
            parameters={
                "input": text
            },
        )

        data = json.loads(workflow.data)

        return data['data']