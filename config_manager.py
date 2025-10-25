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

import json
import yaml
import os
import queue
import numpy as np
from logger import logger
from typing import Dict, Any, Optional, Tuple
import importlib
import cv2

# 全局引用，用于访问正在运行的会话
global_nerfreals = None

# 配置管理辅助函数
def get_config_path() -> str:
    """获取配置文件的路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'conf', 'app_config.yaml')

def load_config() -> Dict[str, Any]:
    """从配置文件加载配置"""
    config_path = get_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        return {}

def save_config(config: Dict[str, Any]) -> bool:
    """保存配置到文件"""
    config_path = get_config_path()
    try:
        # 确保配置目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        logger.info("Configuration saved successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to save config file: {e}")
        return False

class ConfigManager:
    """配置管理类，提供配置的读取、修改和保存功能"""
    
    def __init__(self, app=None):
        """初始化配置管理器"""
        self.app = app
        self._config = load_config()
        self.app_context = None  # AppContext引用
        
    def set_app_context(self, app_context):
        """设置AppContext引用"""
        self.app_context = app_context
        logger.info("AppContext set in ConfigManager")
    
    def get_nerfreals(self):
        """获取nerfreals引用"""
        if self.app_context:
            return self.app_context.nerfreals
        return None
    
    def get_avatar(self):
        """获取avatar引用"""
        if self.app_context:
            return self.app_context.avatar
        return None
    
    def update_avatar(self, new_avatar):
        """更新avatar引用"""
        if self.app_context:
            self.app_context.avatar = new_avatar
            return True
        return False
    
    def update_opt_avatar(self, new_avatar):
        """更新opt中的avatar引用"""
        if self.app_context and hasattr(self.app_context, 'opt'):
            if hasattr(self.app_context.opt, 'avatar'):
                self.app_context.opt.avatar = new_avatar
                return True
        return False
        
    def set_nerfreals_reference(self, nerfreals):
        """
        设置对全局nerfreals字典的引用，用于配置更新时刷新会话
        
        Args:
            nerfreals: 全局会话字典的引用
        """
        global global_nerfreals
        global_nerfreals = nerfreals
        
    def get_config(self, section: str = None, key: str = None) -> Any:
        """
        获取配置
        
        Args:
            section: 配置部分名称
            key: 配置项名称
            
        Returns:
            配置值
        """
        if not section:
            return self._config
        
        if section not in self._config:
            logger.warning(f"Section {section} not found in config")
            return None
        
        if not key:
            return self._config[section]
        
        if key not in self._config[section]:
            logger.warning(f"Key {key} not found in section {section}")
            return None
        
        return self._config[section][key]
    
    def update_config(self, section: str, key: str, value: Any) -> bool:
        """
        更新配置（只更新内存中的配置，不写入配置文件）
        
        Args:
            section: 配置部分名称
            key: 配置项名称
            value: 新的配置值
            
        Returns:
            是否更新成功
        """
        if section not in self._config:
            self._config[section] = {}
            
        old_value = self._config[section].get(key)
        if old_value == value:
            logger.info(f"Config {section}.{key} is already {value}, no update needed")
            return True
        
        self._config[section][key] = value
        logger.info(f"Updated config {section}.{key}: {old_value} -> {value}")
        
        # 不保存到文件，只更新内存中的配置
        return True
    
    def get_model_config(self) -> Dict[str, Any]:
        """获取模型相关配置"""
        llm_type = self.get_config('server', 'llm_type')
        llm = self.get_config('llm')
        return {
            'model': self.get_config('server', 'model'),
            'avatar_id': self.get_config('server', 'avatar_id'),
            'llm_type': llm_type,
            'llm': llm
        }
    
    def update_model_config(self, update_config : Dict[str, Any]) -> Dict[str, Any]:
        """
        更新模型配置，包括头像ID、LLM类型和LLM配置等
        
        Args:
            update_config: 包含模型配置的字典
        
        Returns:
            dict: 更新后的配置
        """
        import time
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 1. 更新头像
            # 保存旧的头像ID，用于判断是否需要更新全局头像
            old_avatar_id = self.get_config('server', 'avatar_id')
            logger.info(f"Current avatar ID: {old_avatar_id}")
            
            # 获取新的头像ID
            new_avatar_id = update_config.get('avatar_id')
            logger.info(f"Updated avatar ID to: {new_avatar_id}")
            
            # 如果头像ID发生变化，尝试更新全局头像和所有活跃会话
            if new_avatar_id != old_avatar_id:
                self.update_config('server', 'avatar_id', new_avatar_id)
                logger.info(f"Avatar ID changed from {old_avatar_id} to {new_avatar_id}, initiating global avatar update")
                self._refresh_all_avatars(new_avatar_id)

            # 2. 更新LLM类型
            new_llm_type = update_config.get('llm_type')
            if new_llm_type:
                self.update_config('server', 'llm_type', new_llm_type)
                logger.info(f"Updated LLM type to: {new_llm_type}")

            
            # 3. 更新LLM配置
            llm_config_new = update_config.get('llm_config').get(new_llm_type)
            if llm_config_new:
                self.update_config('llm', new_llm_type, llm_config_new)
                logger.info(f"Updated LLM config for {new_llm_type}")


            logger.info(f"Updated configs: {update_config}")
            logger.info(f"self._config: {self._config}")
            
            # 记录总耗时
            end_time = time.time()
            logger.info(f"Model configuration update completed in {end_time - start_time:.2f}s")
            
            # 返回更新后的配置
            return self.get_model_config()
            
        except Exception as e:
            logger.error(f"Failed to update model config: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            # 返回当前配置
            return self.get_model_config()
            
    def _refresh_all_avatars(self, new_avatar_id):
        """
        刷新所有活跃会话的头像资源
        
        Args:
            new_avatar_id: 新的头像ID
        """
        import gc
        import torch
        
        try:
            # 获取当前配置的模型类型
            current_model = self.get_config('server', 'model')
            logger.info(f"Current model: {current_model}")
            
            # 检查current_model是否为None并设置模块名
            if current_model is None:
                logger.warning("Current model is None, using default module 'musereal' for avatar update")
                module_name = 'musereal'  # 默认使用musereal模块
            else:
                # 根据模型类型选择不同的加载模块
                if 'musetalk' in current_model.lower():
                    module_name = 'musereal'
                elif 'wav2lip' in current_model.lower():
                    module_name = 'lipreal'
                else:
                    module_name = 'lightreal'
            
            logger.info(f"Using module: {module_name} to load avatar")
            
            # 动态导入模块并获取加载函数
            module = __import__(module_name, fromlist=['load_avatar'])
            load_avatar_func = getattr(module, 'load_avatar', None)
            
            if load_avatar_func:
                # 获取nerfreals引用
                nerfreals = self.get_nerfreals()
                if nerfreals is None:
                    logger.error("nerfreals not initialized")
                    return
                
                # 预加载avatar数据，避免重复加载
                pre_loaded_avatar = None
                try:
                    pre_loaded_avatar = load_avatar_func(new_avatar_id)
                    logger.info(f"Successfully pre-loaded avatar {new_avatar_id}")
                except Exception as e:
                    logger.error(f"Failed to pre-load avatar {new_avatar_id}: {e}")
                    import traceback
                    logger.error(f"Error traceback: {traceback.format_exc()}")
                    return
                
                # 确定模型类型（只需计算一次）
                model_type = ""
                if 'musetalk' in current_model.lower():
                    model_type = 'musetalk'
                elif 'wav2lip' in current_model.lower():
                    model_type = 'lipreal'
                else:
                    model_type = 'lightreal'
                
                # 如果有活跃会话，更新每个会话的头像
                if nerfreals:
                    success_count = 0
                    failed_count = 0
                    
                    for sessionid, nerfreal in nerfreals.items():
                        try:
                            # 直接使用预加载的avatar数据，避免重复调用load_avatar_func
                            self._update_generic_avatar_direct(nerfreal, sessionid, new_avatar_id, pre_loaded_avatar, model_type)
                            
                            # 重置会话状态，确保新avatar生效
                            self._reset_session_state(nerfreal, sessionid)
                            
                            # 强制垃圾回收，确保旧资源被释放
                            gc.collect()
                            
                            logger.info(f"Successfully refreshed avatar for session {sessionid}")
                            success_count += 1
                            
                        except Exception as e:
                            logger.error(f"Failed to refresh avatar for session {sessionid}: {e}")
                            import traceback
                            logger.error(f"Error traceback: {traceback.format_exc()}")
                            failed_count += 1
                            # 在异常情况下也尝试垃圾回收
                            gc.collect()
                    
                    # 更新全局avatar变量，确保新连接的会话也能使用新的avatar
                    logger.info(f"Updating global avatar after session updates")
                    
                    # 获取avatar引用并更新（使用预加载的数据）
                    avatar = self.get_avatar()
                    if avatar is not None:
                        self.update_avatar(pre_loaded_avatar)
                    
                    # 所有会话更新完成后，执行全局内存清理
                    logger.info("Global memory cleanup after all avatar updates")
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        logger.info("CUDA cache emptied")
                        
                    logger.info(f"Avatar refresh completed for {success_count} sessions (failed: {failed_count})")
                else:
                    # 如果没有活跃会话，更新全局avatar变量
                    logger.info("No active sessions found, updating global avatar only")
                    
                    # 获取avatar引用并更新（使用预加载的数据）
                    avatar = self.get_avatar()
                    if avatar is not None:
                        self.update_avatar(pre_loaded_avatar)
                        logger.info("Global avatar updated successfully")
                    
                    # 检查是否有默认会话，如果有则更新
                    if 'default' in nerfreals:
                        try:
                            # 使用预加载的avatar数据更新默认会话
                            self._update_generic_avatar_direct(nerfreals['default'], 'default', new_avatar_id, pre_loaded_avatar, model_type)
                                
                            logger.info("Default session avatar updated successfully")
                        except Exception as e:
                            logger.error(f"Failed to update default session avatar: {e}")
            else:
                logger.error(f"Failed to get load_avatar function from module {module_name}")
                
        except Exception as e:
            logger.error(f"Failed to refresh all avatars: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            
    def _cleanup_old_avatar(self, nerfreal, sessionid):
        """清理旧的avatar资源"""
        # 打印当前资源状态（用于调试）
        if hasattr(nerfreal, 'mask_list_cycle'):
            current_mask_status = f"has {len(nerfreal.mask_list_cycle)} items" if nerfreal.mask_list_cycle else "is None"
            logger.debug(f"Before cleanup - Session {sessionid} mask_list_cycle {current_mask_status}")
             
        # 需要清理的属性列表
        avatar_attrs = ['frame_list_cycle', 'mask_list_cycle', 'coord_list_cycle', 
                       'mask_coords_list_cycle', 'input_latent_list_cycle', 'face_list_cycle']
                        
        # 逐一清理属性
        for attr in avatar_attrs:
            if hasattr(nerfreal, attr):
                setattr(nerfreal, attr, None)
                
        # 调用对象自身的cleanup方法
        if hasattr(nerfreal, 'cleanup_avatar'):
            try:
                nerfreal.cleanup_avatar()
                logger.info(f"Old avatar resources cleaned up for session {sessionid}")
            except Exception as e:
                logger.warning(f"Error during avatar cleanup for session {sessionid}: {e}")
                
    def _update_musereal_avatar_with_loaded(self, nerfreal, sessionid, new_avatar):
        """
        使用已加载的avatar资源更新MuseTalk模型
        """
        import gc
        import torch
        
        try:
            # 清除所有与avatar相关的属性
            if hasattr(nerfreal, 'frame_list_cycle'):
                delattr(nerfreal, 'frame_list_cycle')
            if hasattr(nerfreal, 'mask_list_cycle'):
                delattr(nerfreal, 'mask_list_cycle')
            if hasattr(nerfreal, 'coord_list_cycle'):
                delattr(nerfreal, 'coord_list_cycle')
            if hasattr(nerfreal, 'mask_coords_list_cycle'):
                delattr(nerfreal, 'mask_coords_list_cycle')
            if hasattr(nerfreal, 'input_latent_list_cycle'):
                delattr(nerfreal, 'input_latent_list_cycle')
            
            # 设置新的avatar属性 - 正确映射元组元素
            # MuseTalk avatar tuple: (frame_list_cycle, mask_list_cycle, coord_list_cycle, mask_coords_list_cycle, input_latent_list_cycle)
            setattr(nerfreal, 'frame_list_cycle', new_avatar[0])
            setattr(nerfreal, 'mask_list_cycle', new_avatar[1])
            setattr(nerfreal, 'coord_list_cycle', new_avatar[2])
            setattr(nerfreal, 'mask_coords_list_cycle', new_avatar[3])
            setattr(nerfreal, 'input_latent_list_cycle', new_avatar[4])
            
            # 强制垃圾回收，确保旧资源被释放
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            # 添加日志记录，验证mask尺寸
            if hasattr(nerfreal, 'mask_list_cycle') and nerfreal.mask_list_cycle and len(nerfreal.mask_list_cycle) > 0:
                mask_shape = nerfreal.mask_list_cycle[0].shape
                frame_shape = nerfreal.frame_list_cycle[0].shape if nerfreal.frame_list_cycle and len(nerfreal.frame_list_cycle) > 0 else "unknown"
                logger.info(f"Successfully updated MuseReal avatar for session {sessionid}. Mask shape: {mask_shape}, Frame shape: {frame_shape}")
                
            if hasattr(nerfreal, 'avatar_info'):
                nerfreal.avatar_info = getattr(new_avatar, 'avatar_info', {}) if hasattr(new_avatar, 'avatar_info') else {}
            if hasattr(nerfreal, 'avatar_type'):
                nerfreal.avatar_type = 'musetalk'
        except Exception as e:
            logger.error(f"Failed to update MuseReal avatar with loaded resources for session {sessionid}: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            raise
    
    def _update_generic_avatar_direct(self, nerfreal, sessionid, new_avatar_id, pre_loaded_avatar, model_type):
        """
        通用头像更新函数，直接使用预加载的avatar数据，避免重复加载
        
        Args:
            nerfreal: 会话的nerfreal对象
            sessionid: 会话ID
            new_avatar_id: 新的头像ID
            pre_loaded_avatar: 预加载的avatar数据
            model_type: 模型类型
        """
        try:
            # 清理旧的avatar资源
            self._cleanup_old_avatar(nerfreal, sessionid)
            
            # 额外清除MuseTalk特定的属性
            if model_type == 'musetalk':
                for attr in ['frame_list_cycle', 'mask_list_cycle', 'coord_list_cycle', 'mask_coords_list_cycle', 'input_latent_list_cycle']:
                    if hasattr(nerfreal, attr):
                        delattr(nerfreal, attr)
            
            # 更新nerfreal的avatar相关属性（使用预加载的数据）
            if model_type == 'musetalk':
                # 调用专用的MuseTalk头像更新方法
                self._update_musereal_avatar_with_loaded(nerfreal, sessionid, pre_loaded_avatar)
                nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                nerfreal.avatar_id = new_avatar_id
                
                # 添加日志记录，验证mask尺寸
                if hasattr(nerfreal, 'mask_list_cycle') and nerfreal.mask_list_cycle and len(nerfreal.mask_list_cycle) > 0:
                    mask_shape = nerfreal.mask_list_cycle[0].shape
                    frame_shape = nerfreal.frame_list_cycle[0].shape if nerfreal.frame_list_cycle and len(nerfreal.frame_list_cycle) > 0 else "unknown"
                    logger.info(f"Successfully updated MuseReal avatar for session {sessionid}. Mask shape: {mask_shape}, Frame shape: {frame_shape}")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'musetalk'
            elif model_type == 'lipreal':
                # Wav2Lip模型的头像更新 - 需要解包tuple
                if isinstance(pre_loaded_avatar, tuple) and len(pre_loaded_avatar) >= 3:
                    # Wav2Lip avatar tuple: (frame_list_cycle, face_list_cycle, coord_list_cycle)
                    nerfreal.frame_list_cycle, nerfreal.face_list_cycle, nerfreal.coord_list_cycle = pre_loaded_avatar[:3]
                    nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                else:
                    logger.error(f"Invalid avatar format for Wav2Lip: expected tuple with 3+ elements, got {type(pre_loaded_avatar)}")
                    raise ValueError(f"Invalid avatar format for Wav2Lip")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'wav2lip'
                    
            else:
                # 其他模型的头像更新（如LightReal）
                if isinstance(pre_loaded_avatar, tuple) and len(pre_loaded_avatar) >= 3:
                    # LightReal avatar tuple: (model, frame_list_cycle, coord_list_cycle)
                    nerfreal.model, nerfreal.frame_list_cycle, nerfreal.coord_list_cycle = pre_loaded_avatar[:3]
                    if len(pre_loaded_avatar) > 3:
                        nerfreal.face_list_cycle = pre_loaded_avatar[3]
                    nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                else:
                    logger.error(f"Invalid avatar format for LightReal: expected tuple with 3+ elements, got {type(pre_loaded_avatar)}")
                    raise ValueError(f"Invalid avatar format for LightReal")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'generic'
            
            logger.info(f"Successfully updated avatar for session {sessionid} using {model_type} model")
            
            # 验证avatar数据一致性
            if hasattr(nerfreal, 'validate_avatar_data') and callable(getattr(nerfreal, 'validate_avatar_data')):
                is_valid, validation_msg = nerfreal.validate_avatar_data()
                if not is_valid:
                    logger.error(f"Avatar data validation failed for session {sessionid}: {validation_msg}")
                    raise ValueError(f"Avatar data validation failed: {validation_msg}")
                else:
                    logger.info(f"Avatar data validation passed for session {sessionid}: {validation_msg}")
            
        except Exception as e:
            logger.error(f"Failed to update generic avatar for session {sessionid}: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            raise

    def _update_generic_avatar(self, nerfreal, sessionid, new_avatar_id, load_avatar_func, model_type):
        """
        通用头像更新函数，适用于所有模型类型
        
        Args:
            nerfreal: 会话的nerfreal对象
            sessionid: 会话ID
            new_avatar_id: 新的头像ID
            load_avatar_func: 头像加载函数
            model_type: 模型类型
        """
        try:
            # 清理旧的avatar资源
            self._cleanup_old_avatar(nerfreal, sessionid)
            
            # 加载新的avatar
            pre_loaded_avatar = load_avatar_func(new_avatar_id)
            
            # 更新nerfreal的avatar相关属性
            if model_type == 'musetalk':
                # MuseTalk模型的头像更新 - 需要解包tuple
                if isinstance(pre_loaded_avatar, tuple) and len(pre_loaded_avatar) >= 5:
                    # MuseTalk avatar tuple: (frame_list_cycle, mask_list_cycle, coord_list_cycle, mask_coords_list_cycle, input_latent_list_cycle)
                    nerfreal.frame_list_cycle, nerfreal.mask_list_cycle, nerfreal.coord_list_cycle, nerfreal.mask_coords_list_cycle, nerfreal.input_latent_list_cycle = pre_loaded_avatar
                    nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                else:
                    logger.error(f"Invalid avatar format for MuseTalk: expected tuple with 5 elements, got {type(pre_loaded_avatar)}")
                    raise ValueError(f"Invalid avatar format for MuseTalk")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'musetalk'
                    
            elif model_type == 'lipreal':
                # Wav2Lip模型的头像更新 - 需要解包tuple
                if isinstance(pre_loaded_avatar, tuple) and len(pre_loaded_avatar) >= 3:
                    # Wav2Lip avatar tuple: (frame_list_cycle, face_list_cycle, coord_list_cycle)
                    nerfreal.frame_list_cycle, nerfreal.face_list_cycle, nerfreal.coord_list_cycle = pre_loaded_avatar[:3]
                    nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                else:
                    logger.error(f"Invalid avatar format for Wav2Lip: expected tuple with 3+ elements, got {type(pre_loaded_avatar)}")
                    raise ValueError(f"Invalid avatar format for Wav2Lip")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'wav2lip'
                    
            else:
                # 其他模型的头像更新（如LightReal）
                if isinstance(pre_loaded_avatar, tuple) and len(pre_loaded_avatar) >= 3:
                    # LightReal avatar tuple: (model, frame_list_cycle, coord_list_cycle)
                    nerfreal.model, nerfreal.frame_list_cycle, nerfreal.coord_list_cycle = pre_loaded_avatar[:3]
                    if len(pre_loaded_avatar) > 3:
                        nerfreal.face_list_cycle = pre_loaded_avatar[3]
                    nerfreal.avatar = pre_loaded_avatar  # 同时保持avatar引用
                else:
                    logger.error(f"Invalid avatar format for LightReal: expected tuple with 3+ elements, got {type(pre_loaded_avatar)}")
                    raise ValueError(f"Invalid avatar format for LightReal")
                    
                if hasattr(nerfreal, 'avatar_info'):
                    nerfreal.avatar_info = getattr(pre_loaded_avatar, 'avatar_info', {}) if hasattr(pre_loaded_avatar, 'avatar_info') else {}
                if hasattr(nerfreal, 'avatar_type'):
                    nerfreal.avatar_type = 'generic'
            
            logger.info(f"Successfully updated avatar for session {sessionid} using {model_type} model")
            
            # 验证avatar数据一致性
            if hasattr(nerfreal, 'validate_avatar_data') and callable(getattr(nerfreal, 'validate_avatar_data')):
                is_valid, validation_msg = nerfreal.validate_avatar_data()
                if not is_valid:
                    logger.error(f"Avatar data validation failed for session {sessionid}: {validation_msg}")
                    raise ValueError(f"Avatar data validation failed: {validation_msg}")
                else:
                    logger.info(f"Avatar data validation passed for session {sessionid}: {validation_msg}")
            
        except Exception as e:
            logger.error(f"Failed to update generic avatar for session {sessionid}: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            raise
            
    def _reset_session_state(self, nerfreal, sessionid):
        """
        重置会话状态，确保新avatar生效
        
        Args:
            nerfreal: 会话的nerfreal对象
            sessionid: 会话ID
        """
        try:
            # 1. 重置索引，确保从新的avatar开始
            if hasattr(nerfreal, 'idx'):
                nerfreal.idx = 0
                logger.debug(f"Reset idx to 0 for session {sessionid}")
            
            # 2. 清除res_frame_queue中的所有旧帧，避免使用旧的索引
            if hasattr(nerfreal, 'res_frame_queue') and nerfreal.res_frame_queue:
                try:
                    while not nerfreal.res_frame_queue.empty():
                        try:
                            nerfreal.res_frame_queue.get(block=False)
                            nerfreal.res_frame_queue.task_done()
                        except queue.Empty:
                            break
                    logger.debug(f"Cleared res_frame_queue for session {sessionid}")
                except Exception as e:
                    logger.warning(f"Error clearing res_frame_queue for session {sessionid}: {e}")
            
            # 清除其他可能影响显示的队列或缓冲区
            for attr_name in ['audio_queue', 'video_buffer', 'frame_buffer']:
                if hasattr(nerfreal, attr_name):
                    attr = getattr(nerfreal, attr_name)
                    if hasattr(attr, 'clear') and callable(getattr(attr, 'clear')):
                        try:
                            attr.clear()
                            logger.info(f"Cleared {attr_name} for session {sessionid}")
                        except Exception as e:
                            logger.warning(f"Error clearing {attr_name} for session {sessionid}: {e}")
                        
            # 调用模型特定的reset方法（如果存在）
            if hasattr(nerfreal, 'reset_avatar_state') and callable(getattr(nerfreal, 'reset_avatar_state')):
                try:
                    nerfreal.reset_avatar_state()
                    logger.info(f"Called model-specific reset for session {sessionid}")
                except Exception as e:
                    logger.warning(f"Error calling model-specific reset for session {sessionid}: {e}")
            
            logger.info(f"Reset session state for {sessionid}")
            
        except Exception as e:
            logger.error(f"Error resetting session state for {sessionid}: {e}")
            # 即使出错也继续，不要中断avatar更新流程
            logger.debug(f"Reset idx to 0 for session {sessionid}")
            
            # 2. 清除res_frame_queue中的所有旧帧，避免使用旧的索引
            if hasattr(nerfreal, 'res_frame_queue') and nerfreal.res_frame_queue:
                try:
                    while not nerfreal.res_frame_queue.empty():
                        try:
                            nerfreal.res_frame_queue.get(block=False)
                            nerfreal.res_frame_queue.task_done()
                        except queue.Empty:
                            break
                    logger.debug(f"Cleared res_frame_queue for session {sessionid}")
                except Exception as e:
                    logger.warning(f"Error clearing res_frame_queue for session {sessionid}: {e}")
    
    def register_routes(self, app):
        """注册配置管理的API路由"""
        # 导入需要的模块
        from aiohttp import web
        import aiohttp_cors
        
        # 获取配置接口
        async def get_config_handler(request):
            try:
                section = request.query.get('section')
                key = request.query.get('key')
                
                config = self.get_config(section, key)
                return web.json_response({
                    'success': True,
                    'data': config
                })
            except Exception as e:
                logger.error(f"Error getting config: {e}")
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        # 更新单个配置接口
        async def update_config_handler(request):
            try:
                data = await request.json()
                section = data.get('section')
                key = data.get('key')
                value = data.get('value')
                
                if not section or not key:
                    return web.json_response({
                        'success': False,
                        'error': 'Section and key are required'
                    })
                
                success = self.update_config(section, key, value)
                return web.json_response({
                    'success': success,
                    'message': 'Config updated successfully' if success else 'Failed to update config'
                })
            except Exception as e:
                logger.error(f"Error updating config: {e}")
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        # 批量更新配置接口
        async def bulk_update_config_handler(request):
            try:
                data = await request.json()
                updates = data.get('updates', {})
                
                if not isinstance(updates, dict):
                    return web.json_response({
                        'success': False,
                        'error': 'Updates must be a dictionary'
                    })
                
                success, failed = self.update_multiple_configs(updates)
                return web.json_response({
                    'success': success,
                    'message': 'All configs updated successfully' if success else 'Some configs failed to update',
                    'failed': failed
                })
            except Exception as e:
                logger.error(f"Error bulk updating config: {e}")
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        # 获取模型配置接口
        async def get_model_config_handler(request):
            try:
                config = self.get_model_config()
                return web.json_response({
                    'success': True,
                    'data': config
                })
            except Exception as e:
                logger.error(f"Error getting model config: {e}")
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        # 更新模型配置接口
        async def update_model_config_handler(request):
            try:
                data = await request.json()

                logger.info(f"Received model config update request: {data}")
                # 创建一个包含所有模型配置的字典
                update_config = {
                    'model': data.get('model'),
                    'avatar_id': data.get('avatar_id'),
                    'llm_type': data.get('llm_type'),
                    'llm_config': data.get('llm_config')
                }
                
                # # 添加LLM配置（如果有）
                # llm_config_new = data.get('llm_config')
                # if llm_config_new and update_config.get('llm_type'):
                #     update_config['llm'] = {
                #         update_config['llm_type']: llm_config_new
                #     }

                logger.info(f"Update config prepared: {update_config}")
                
                # 调用更新模型配置的方法
                result = self.update_model_config(update_config)
                
                # 格式化响应
                if isinstance(result, dict) and 'success' in result:
                    return web.json_response({
                        'success': result['success'],
                        'message': 'Model config updated successfully' if result['success'] else 'Failed to update model config',
                        'error': result.get('error')
                    })
                else:
                    # 对于旧版本兼容性的处理
                    return web.json_response({
                        'success': True,
                        'message': 'Model config updated successfully'
                    })
            except Exception as e:
                logger.error(f"Error updating model config: {e}")
                import traceback
                logger.error(f"Update model config handler error traceback: {traceback.format_exc()}")
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        # 注册路由
        app.router.add_get('/api/config', get_config_handler)
        app.router.add_post('/api/config', update_config_handler)
        app.router.add_post('/api/config/bulk', bulk_update_config_handler)
        app.router.add_get('/api/config/model', get_model_config_handler)
        app.router.add_post('/api/config/model', update_model_config_handler)
        
        # 配置CORS
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "OPTIONS"]
            )
        })
        
        # 为配置路由添加CORS
        for route in app.router.routes():
            if route.resource and str(route.resource).startswith('/api/config'):
                cors.add(route)
                logger.info(f"Added CORS to config route: {route}")

# 创建全局配置管理器实例
g_config_manager = ConfigManager()