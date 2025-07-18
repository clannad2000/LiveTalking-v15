import time
import os
from basereal import BaseReal
from logger import logger
import llm_coze

def llm_response(text, nerfreal:BaseReal, type):
    if type == "opai":
        return opai_response(text, nerfreal)
    elif type == "coze":
        return coze_response(text, nerfreal)
    else:
        raise ValueError(f"Unsupported LLM type: {type}")
    
def opai_response(message, nerfreal:BaseReal):
    start = time.perf_counter()
    from openai import OpenAI
    client = OpenAI(
        # 如果您没有配置环境变量，请在此处用您的API Key进行替换
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        # 填写DashScope SDK的base_url
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    end = time.perf_counter()
    logger.info(f"llm Time init: {end-start}s")
    completion = client.chat.completions.create(
        model="qwen-plus",
        messages=[{'role': 'system', 'content': 'You are a helpful assistant.'},
                  {'role': 'user', 'content': message}],
        stream=True,
        # 通过以下设置，在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": True}
    )
    result=""
    first = True
    for chunk in completion:
        if len(chunk.choices)>0:
            #print(chunk.choices[0].delta.content)
            if first:
                end = time.perf_counter()
                logger.info(f"llm Time to first chunk: {end-start}s")
                first = False
            msg = chunk.choices[0].delta.content
            lastpos=0
            #msglist = re.split('[,.!;:，。！?]',msg)
            for i, char in enumerate(msg):
                if char in ",.!;:，。！？：；" :
                    result = result+msg[lastpos:i+1]
                    lastpos = i+1
                    if len(result)>10:
                        logger.info(result)
                        nerfreal.put_msg_txt(result)
                        result=""
            result = result+msg[lastpos:]
    end = time.perf_counter()
    logger.info(f"llm Time to last chunk: {end-start}s")
    nerfreal.put_msg_txt(result)  
    return result
    
def coze_response(text, nerfreal:BaseReal):
    start = time.perf_counter()
    coze = llm_coze.CozeWorkflow()
    response = coze.chat_with_coze(text)
    end = time.perf_counter()
    logger.info(f"llm_coze Time to last chunk: {end-start}s")
    nerfreal.put_msg_txt(response)

    return response