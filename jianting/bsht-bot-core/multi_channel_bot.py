"""
多频道对讲机监听录音系统

同时监听多个频道，记录所有通联音频。
纯监听模式 — 不需要 PyAudio / 麦克风 / 扬声器。

Usage:
    python multi_channel_bot.py
    
    或指定配置文件:
    python multi_channel_bot.py --config channels.json

配置文件格式 (channels.json):
    {
        "username": "bswxd",
        "password": "BsWxd2026",
        "recordings_dir": "recordings",
        "enable_audio_processing": true,
        "channels": [
            {"id": 28951, "name": "频道A", "passcode": 0},
            {"id": 62793, "name": "频道B", "passcode": 0}
        ]
    }
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
from typing import List, Dict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("multi_channel.log", encoding='utf-8')
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logger = logging.getLogger("MultiChannelBot")


class MultiChannelBot:
    """
    多频道监听录音机器人
    
    共享一个 BSHTClient 登录，为每个频道创建独立的 ChannelWorker。
    """
    
    DEFAULT_CONFIG = {
        "username": "",
        "password": "",
        "recordings_dir": "recordings",
        "enable_audio_processing": True,
        "channels": []
    }
    
    def __init__(self, config: dict):
        self.config = config
        self.client = None
        self.workers: List = []
        self._is_running = False
    
    def start(self):
        """启动多频道监听"""
        from bsht_client import BSHTClient
        from channel_worker import ChannelWorker
        
        channels = self.config.get("channels", [])
        if not channels:
            logger.error("未配置任何频道!")
            return
        
        # 1. 登录
        logger.info("正在登录...")
        self.client = BSHTClient()
        
        username = self.config["username"]
        password = self.config["password"]
        
        # 尝试加载本地凭证
        if os.path.exists("credentials.json"):
            try:
                with open("credentials.json", 'r') as f:
                    creds = json.load(f)
                if creds.get("access_token"):
                    self.client._token_manager._access_token = creds["access_token"]
                    self.client._token_manager._refresh_token = creds.get("refresh_token", "")
                    # 验证 token
                    verify = self.client.get_user_channels()
                    if verify.success:
                        logger.info("已加载本地凭证")
                    else:
                        raise ValueError("凭证已过期")
            except Exception:
                logger.info("本地凭证无效，重新登录...")
                login = self.client.login(username, password)
                if not login.success:
                    logger.error(f"登录失败: {login.error}")
                    return
                logger.info(f"登录成功: {login.data.nickname} ({login.data.user_id})")
        else:
            login = self.client.login(username, password)
            if not login.success:
                logger.error(f"登录失败: {login.error}")
                return
            logger.info(f"登录成功: {login.data.nickname} ({login.data.user_id})")
        
        # 2. 创建录音根目录
        recordings_dir = self.config.get("recordings_dir", "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        
        enable_processing = self.config.get("enable_audio_processing", True)
        
        # 3. 为每个频道创建 Worker
        self._is_running = True
        for ch_config in channels:
            ch_id = ch_config.get("id") or ch_config.get("channel_id")
            ch_name = ch_config.get("name", "")
            ch_pass = ch_config.get("passcode", 0)
            
            if not ch_id:
                logger.warning(f"频道配置缺少 id: {ch_config}")
                continue
            
            worker = ChannelWorker(
                client=self.client,
                channel_id=ch_id,
                channel_name=ch_name,
                channel_passcode=ch_pass,
                recordings_dir=recordings_dir,
                enable_audio_processing=enable_processing,
                headless=True,
            )
            worker.start()
            self.workers.append(worker)
            
            # 频道间稍作延时，避免并发请求过多
            time.sleep(1)
        
        logger.info(f"🎧 已启动 {len(self.workers)} 个频道监听")
        logger.info(f"📁 录音保存到: {os.path.abspath(recordings_dir)}")
        logger.info("按 Ctrl+C 停止...")
        
        # 4. 主线程保活
        try:
            while self._is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def stop(self):
        """停止所有频道"""
        logger.info("正在停止所有频道...")
        self._is_running = False
        for worker in self.workers:
            worker.stop()
        self.workers.clear()
        logger.info("所有频道已停止")


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 默认配置文件路径
    default_paths = ["channels.json", "config.json"]
    for path in default_paths:
        if os.path.exists(path):
            logger.info(f"加载配置文件: {path}")
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    return None


def create_example_config():
    """生成示例配置文件"""
    config = {
        "username": "your_username",
        "password": "your_password",
        "recordings_dir": "recordings",
        "enable_audio_processing": True,
        "channels": [
            {"id": 28951, "name": "频道A", "passcode": 0},
            {"id": 62793, "name": "频道B", "passcode": 0}
        ]
    }
    path = "channels.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info(f"已生成示例配置: {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BSHT 多频道对讲机监听录音系统")
    parser.add_argument("--config", "-c", help="配置文件路径 (JSON)")
    parser.add_argument("--init", action="store_true", help="生成示例配置文件")
    args = parser.parse_args()
    
    if args.init:
        create_example_config()
        sys.exit(0)
    
    config = load_config(args.config)
    
    if not config:
        logger.error("未找到配置文件! 使用 --init 生成示例配置:")
        logger.error("  python multi_channel_bot.py --init")
        logger.error("  然后编辑 channels.json 填入账号和频道信息")
        sys.exit(1)
    
    if not config.get("username") or not config.get("password"):
        logger.error("配置文件缺少 username 或 password!")
        sys.exit(1)
    
    if not config.get("channels"):
        logger.error("配置文件中未配置任何频道!")
        sys.exit(1)
    
    bot = MultiChannelBot(config)
    
    # 优雅退出
    def signal_handler(sig, frame):
        logger.info("收到停止信号...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot.start()
