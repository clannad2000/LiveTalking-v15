from typing import Dict
from core.models.basereal import BaseReal
from utils.logger import logger


class Nerfreals:
    def __init__(self):
        # 初始化一个空的字典来存储Nerfreals
        # 键是sessionid，值是一个列表[BaseReal, int]，int 为0表示未使用，1表示正在使用
        self.nerfreals = {}
    
    def get_nerfreal(self, sessionid: str) -> BaseReal:
        # 首先查看default nerfreal
        if 'default' in self.nerfreals and self.nerfreals['default'][0].sessionid == sessionid:
            return self.nerfreals['default'][0]

        if sessionid in self.nerfreals:
            return self.nerfreals[sessionid][0]
        else:
            raise KeyError(f"Nerfreal with sessionid '{sessionid}' not found.")
        
    def is_nerfreal_exist(self, sessionid: str) -> bool:
        # 检查指定sessionid的Nerfreal是否存在
        if 'default' in self.nerfreals and self.nerfreals['default'][0].sessionid == sessionid:
            return True
        return sessionid in self.nerfreals
        
    def _build_nerfreal(self, sessionid: str, opt, model, avatar) -> BaseReal:
        try:
            if opt.model == 'wav2lip':
                from core.models.lipreal.lipreal import LipReal
                nerfreal = LipReal(opt,model,avatar)
            elif opt.model == 'musetalk' or opt.model == 'musetalkv15':
                from core.models.musereal.musereal import MuseReal
                nerfreal = MuseReal(opt,model,avatar)
            # elif opt.model == 'ernerf':
            #     from nerfreal import NeRFReal
            #     nerfreal = NeRFReal(opt,model,avatar)
            elif opt.model == 'ultralight':
                from core.models.lightreal.lightreal import LightReal
                nerfreal = LightReal(opt,model,avatar)
            else:
                raise ValueError(f"Unsupported model type: {opt.model}")
            logger.info(f'Created nerfreal for sessionid={sessionid}')
            return nerfreal
        except ImportError as e:
            logger.error(f'build nerfreal failed:{e}')
        
    def build_default_nerfreal(self, opt, model, avatar):
        opt.sessionid = 'default'
        nerfreal = self._build_nerfreal('default', opt, model, avatar)
        self.nerfreals['default'] = [nerfreal, 0]
        

        
    def build_normal_nerfreal(self, sessionid: str, opt, model, avatar):
        # 如果nerfreals['default']未被使用，则使用default的BaseReal实例
        if 'default' in self.nerfreals and self.nerfreals['default'][1] == 0:
            self.nerfreals['default'][1] = 1
            self.nerfreals['default'][0].sessionid = sessionid
            logger.info(f'Using existing nerfreal for sessionid=default,set sessionid={sessionid}')
            return

        # 如果不存在nerfreals['default']，则创建一个新的BaseReal实例
        opt.sessionid = sessionid
        nerfreal = self._build_nerfreal(sessionid, opt, model, avatar)
        self.nerfreals[sessionid] = (nerfreal, 1)

    def length(self) -> int:
        # 返回当前Nerfreals的数量
        return len(self.nerfreals)
    
    def delete_nerfreal(self, sessionid: str):
        # 首先查看default nerfreal
        if 'default' in self.nerfreals and self.nerfreals['default'][0].sessionid == sessionid:
            del self.nerfreals['default']
            logger.info(f'Deleted default nerfreal,sessionid={sessionid}')
            return

        # 删除指定sessionid的Nerfreal
        if sessionid in self.nerfreals:
            del self.nerfreals[sessionid]
            logger.info(f'Deleted nerfreal for sessionid={sessionid}')
        else:
            logger.warning(f'Nerfreal with sessionid {sessionid} does not exist.')