"""
配置管理模块 - 使用环境变量管理配置
高内聚低耦合设计
"""
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class BSHTConfig:
    """BSHT账号配置"""
    username: str
    password: str
    channel_id: int
    channel_passcode: int = 0


@dataclass
class APIConfig:
    """AI API配置"""
    siliconflow_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"


@dataclass
class DSPConfig:
    """DSP处理配置"""
    enabled: bool = True
    algorithm: str = "timedomain"  # timedomain, spectral, wiener, rnnoise
    agc_mode: str = "webrtc"
    vad_enabled: bool = False
    # SNR阈值配置
    snr_threshold_high: float = 20.0  # SNR > 20 不需要处理
    snr_threshold_low: float = 10.0   # SNR < 10 需要处理


@dataclass
class DatabaseConfig:
    """数据库配置"""
    path: str = "data/records.db"
    max_records: int = 10000


@dataclass
class AppConfig:
    """应用完整配置"""
    bsht: BSHTConfig
    api: APIConfig
    dsp: DSPConfig
    database: DatabaseConfig
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """从环境变量加载配置"""
        # BSHT配置
        bsht = BSHTConfig(
            username=os.getenv("BSHT_USERNAME", ""),
            password=os.getenv("BSHT_PASSWORD", ""),
            channel_id=int(os.getenv("BSHT_CHANNEL_ID", "0")),
            channel_passcode=int(os.getenv("BSHT_CHANNEL_PASSCODE", "0"))
        )
        
        # API配置
        api = APIConfig(
            siliconflow_key=os.getenv("SILICONFLOW_API_KEY", ""),
            base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        )
        
        # DSP配置
        dsp = DSPConfig(
            enabled=os.getenv("DSP_ENABLED", "true").lower() == "true",
            algorithm=os.getenv("DSP_ALGORITHM", "timedomain"),
            agc_mode=os.getenv("DSP_AGC_MODE", "webrtc"),
            vad_enabled=os.getenv("DSP_VAD_ENABLED", "false").lower() == "true",
            snr_threshold_high=float(os.getenv("DSP_SNR_THRESHOLD_HIGH", "20.0")),
            snr_threshold_low=float(os.getenv("DSP_SNR_THRESHOLD_LOW", "10.0"))
        )
        
        # 数据库配置
        database = DatabaseConfig(
            path=os.getenv("DATABASE_PATH", "data/records.db"),
            max_records=int(os.getenv("DATABASE_MAX_RECORDS", "10000"))
        )
        
        return cls(bsht=bsht, api=api, dsp=dsp, database=database)
    
    def validate(self) -> tuple[bool, str]:
        """验证配置完整性"""
        if not self.bsht.username or not self.bsht.password:
            return False, "BSHT账号密码未配置"
        if self.bsht.channel_id <= 0:
            return False, "频道ID未配置"
        if self.dsp.enabled and not self.api.siliconflow_key:
            return False, "DSP启用时需要配置API Key"
        return True, "配置完整"


# 全局配置实例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def reload_config() -> AppConfig:
    """重新加载配置"""
    global _config
    _config = AppConfig.from_env()
    return _config


def set_config(config: AppConfig):
    """设置全局配置"""
    global _config
    _config = config
