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

    async def send_async(self, title: str, content: str, userid: Optional[str] = None) -> bool:
        """
        异步发送推送消息

        Args:
            title: 消息标题
            content: 消息内容
            userid: 指定用户ID，为None则推送给所有目标

        Returns:
            是否发送成功
        """
        import httpx

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.url, json=params)
                result = response.json()

                success = (
                    result.get("errcode") == 0 or
                    result.get("code") == 0 or
                    "ok" in str(result.get("msg", "")).lower() or
                    "success" in str(result.get("msg", "")).lower() or
                    result.get("success") == True
                )

                if success:
                    logger.info(f"[WxPusher] 异步推送成功: {title}")
                    return True
                else:
                    logger.warning(f"[WxPusher] 异步推送失败: {result}")
                    return False

        except Exception as e:
            logger.error(f"[WxPusher] 异步推送异常: {e}")
            return False


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


# 全局推送器实例（用于热更新）
_global_pusher = None


def get_pusher() -> Optional[WxPusher]:
    """获取全局推送器实例"""
    global _global_pusher
    return _global_pusher


def set_pusher(pusher: Optional[WxPusher]):
    """设置全局推送器实例"""
    global _global_pusher
    _global_pusher = pusher


def reload_pusher() -> Optional[WxPusher]:
    """热更新：从数据库重新加载推送配置"""
    global _global_pusher

    try:
        import sqlite3
        import os

        # 获取数据库路径
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'records.db'
        )

        if not os.path.exists(db_path):
            logger.warning("[WxPusher] 数据库不存在，使用环境变量")
            return load_pusher_from_env()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取启用的 WxPusher 服务
        cursor.execute("""
            SELECT url, token FROM notify_services
            WHERE type = 'wxpusher' AND enabled = 1
            LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            conn.close()
            logger.info("[WxPusher] 数据库中无启用的推送服务")
            return load_pusher_from_env()

        url, token = row

        if not url:
            conn.close()
            logger.warning("[WxPusher] 数据库中未配置 URL")
            return None

        # 获取推送目标
        cursor.execute("""
            SELECT user_identifier, name, keywords
            FROM notify_users
            WHERE enabled = 1
        """)
        user_rows = cursor.fetchall()
        conn.close()

        targets = []
        for user_identifier, name, keywords in user_rows:
            # keywords 可能是逗号分隔的字符串或空
            kw_list = []
            if keywords:
                kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            targets.append(PushTarget(userid=user_identifier, name=name, keywords=kw_list))

        if not targets:
            logger.warning("[WxPusher] 数据库中无推送目标")
            return None

        # 创建新的推送器
        new_pusher = WxPusher(url=url, token=token or "", targets=targets)
        _global_pusher = new_pusher

        logger.info(f"[WxPusher] 热更新成功: {url}, {len(targets)} 个目标")
        return new_pusher

    except Exception as e:
        logger.error(f"[WxPusher] 热更新失败: {e}")
        # 失败时尝试使用环境变量
        return load_pusher_from_env()


def load_pusher_from_env() -> Optional[WxPusher]:
    """从环境变量加载推送配置（备用）"""
    global _global_pusher
    pusher = load_pusher()
    _global_pusher = pusher
    return pusher


def init_pusher_from_env_migration():
    """初始化：从环境变量迁移到数据库（只执行一次）"""
    try:
        import sqlite3
        import os
        import json

        # 获取数据库路径
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'records.db'
        )

        if not os.path.exists(db_path):
            return False

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查是否已有 WxPusher 服务
        cursor.execute("SELECT COUNT(*) FROM notify_services WHERE type = 'wxpusher'")
        count = cursor.fetchone()[0]

        if count > 0:
            conn.close()
            logger.info("[WxPusher] 数据库已有配置，跳过迁移")
            return True

        # 从环境变量加载
        from src.config import load_env_file
        load_env_file()

        url = os.getenv("WXPUSH_URL", "").strip()
        token = os.getenv("WXPUSH_TOKEN", "").strip()
        target_str = os.getenv("WXPUSH_TARGETS", "").strip()

        if not url:
            conn.close()
            return False

        # 创建服务
        cursor.execute("""
            INSERT INTO notify_services (name, type, url, token, config, enabled)
            VALUES (?, ?, ?, ?, ?, 1)
        """, ("WxPusher", "wxpusher", url, token, json.dumps({})))

        service_id = cursor.lastrowid

        # 创建用户
        if target_str:
            for target_item in target_str.split(";"):
                if not target_item.strip():
                    continue
                parts = target_item.split(":")
                userid = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else userid
                keywords = parts[2].strip() if len(parts) > 2 else ""

                cursor.execute("""
                    INSERT INTO notify_users (service_id, name, user_identifier, keywords, enabled)
                    VALUES (?, ?, ?, ?, 1)
                """, (service_id, name, userid, keywords))

        conn.commit()
        conn.close()

        logger.info("[WxPusher] 配置已从环境变量迁移到数据库")
        return True

    except Exception as e:
        logger.error(f"[WxPusher] 迁移失败: {e}")
        return False