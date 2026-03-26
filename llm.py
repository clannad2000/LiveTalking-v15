import time
import os
from basereal import BaseReal
from logger import logger
import llm_coze
import re
from config_manager import g_config_manager

def llm_response(text, nerfreal:BaseReal, llm_type):
    if llm_type == "openai":
        return opai_response(text, nerfreal)
    elif llm_type == "coze":
        return coze_response(text, nerfreal)
    else:
        raise ValueError(f"Unsupported LLM type: {llm_type}")
    
def opai_response(message, nerfreal:BaseReal):
    start = time.perf_counter()
    
    # 从配置管理器获取参数
    llm = g_config_manager.get_config('llm')
    llm_config = llm.get('openai', {}) if llm else {}
    
    # 处理嵌套的openai配置结构
    if isinstance(llm_config, dict) and 'openai' in llm_config:
        llm_config = llm_config['openai']
    
    # 处理api_key
    api_key = llm_config.get('api_key', '')
    base_url = llm_config.get('base_url', "")
    
    # 如果配置中没有api_key，回退到直接从环境变量获取
    if not api_key:
        raise ValueError("OPAI_API_KEY 未配置")
    
    if not base_url:
        raise ValueError("OPAI_API_BASE_URL 未配置")
    
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    
    end = time.perf_counter()
    logger.info(f"llm Time init: {end-start}s")
    
    completion = client.chat.completions.create(
        model=llm_config.get('model', "qwen-plus"),
        messages=[
            {'role': 'system', 'content': llm_config.get('system_prompt', 'You are a helpful assistant.')},
            {'role': 'user', 'content': message}
        ],
        stream=llm_config.get('stream', True),
        stream_options=llm_config.get('stream_options', {"include_usage": True})
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

    # 把response中的内容按句号，问号，感叹号分割
    sentences = re.split('[。？！]', response)
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            nerfreal.put_msg_txt(sentence)

    return response