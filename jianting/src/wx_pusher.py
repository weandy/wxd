"""
微信推送模块 - 基于 go-wxpush 服务
支持关键词触发推送
"""
import os
import logging
import requests
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger("WxPusher")


@dataclass
class PushTarget:
    """推送目标配置"""
    userid: str           # 微信 OpenID
    name: str             # 备注名称
    keywords: List[str]   # 关键词列表，为空表示接收所有


class WxPusher:
    """微信消息推送器"""
    
    def __init__(self, url: str, token: str, targets: List[PushTarget]):
        # 确保URL正确拼接
        url = url.rstrip('/')
        if not url.endswith('/wxsend'):
            url = url + "/wxsend"
        self.url = url
        self.token = token
        self.targets = targets
        self.session = requests.Session()
    
    def send(self, title: str, content: str, userid: Optional[str] = None) -> bool:
        """
        发送推送消息
        
        Args:
            title: 消息标题
            content: 消息内容
            userid: 指定用户ID，为None则推送给所有目标
            
        Returns:
            是否发送成功
        """
        # 构建请求参数
        params = {
            "title": title,
            "content": content,
        }
        
        if userid:
            params["userid"] = userid
        
        # 添加 token
        if self.token:
            params["token"] = self.token
        
        try:
            response = self.session.post(self.url, json=params, timeout=10)
            result = response.json()
            
            # 检查多种成功标志
            # 1. errcode == 0
            # 2. msg 包含 "ok" 或 "success"
            # 3. 直接成功（无错误）
            success = (
                result.get("errcode") == 0 or
                result.get("code") == 0 or
                "ok" in str(result.get("msg", "")).lower() or
                "success" in str(result.get("msg", "")).lower() or
                result.get("success") == True
            )
            
            if success:
                logger.info(f"[WxPusher] 推送成功: {title}")
                return True
            else:
                logger.warning(f"[WxPusher] 推送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"[WxPusher] 推送异常: {e}")
            return False
    
    def send_to_matched(self, text: str, title: str, content: str) -> List[str]:
        """
        根据关键词匹配发送推送
        
        Args:
            text: 识别的文本（用于匹配关键词）
            title: 消息标题
            content: 消息内容
            
        Returns:
            成功推送的用户列表
        """
        text_upper = text.upper()
        sent_users = []
        
        for target in self.targets:
            # 检查是否匹配关键词
            if target.keywords:
                matched = any(kw.upper() in text_upper for kw in target.keywords)
                if not matched:
                    continue
            
            # 发送推送
            if self.send(title, content, target.userid):
                sent_users.append(target.name)
        
        return sent_users


def load_pusher(env_path: str = ".env") -> Optional[WxPusher]:
    """从环境变量加载推送配置"""
    # 加载 .env 文件
    from src.config import load_env_file
    load_env_file(env_path)
    
    url = os.getenv("WXPUSH_URL", "").strip()
    if not url:
        logger.info("[WxPusher] 未配置推送服务")
        return None
    
    token = os.getenv("WXPUSH_TOKEN", "").strip()
    
    # 解析推送目标
    targets = []
    target_str = os.getenv("WXPUSH_TARGETS", "")
    if target_str:
        # 格式: userid:名称:关键词1,关键词2;userid:名称
        for target_item in target_str.split(";"):
            if not target_item.strip():
                continue
            parts = target_item.split(":")
            userid = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else userid
            keywords = [k.strip() for k in parts[2].split(",")] if len(parts) > 2 else []
            
            targets.append(PushTarget(userid=userid, name=name, keywords=keywords))
    
    if not targets:
        logger.warning("[WxPusher] 未配置推送目标")
        return None
    
    pusher = WxPusher(url=url, token=token, targets=targets)
    logger.info(f"[WxPusher] 已加载: {url}, {len(targets)} 个目标")
    return pusher