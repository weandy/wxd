"""
配置管理模块 - 使用环境变量管理配置
支持 .env 文件和系统环境变量
高内聚低耦合设计
"""
import os
from typing import Optional
from dataclasses import dataclass


def load_env_file(env_path: str = ".env") -> None:
    """从 .env 文件加载环境变量"""
    if not os.path.exists(env_path):
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue
            
            # 解析 KEY=VALUE 格式 - 先去掉行内注释
            if '#' in line:
                line = line.split('#')[0].strip()
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                # 只有当环境变量不存在时才设置
                if key not in os.environ:
                    os.environ[key] = value


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
    # 智谱AI API配置
    zhipu_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    # 专家分析模型配置
    expert_model_enabled: bool = True  # 是否启用专家模型
    expert_model: str = "glm-4-flash"  # 专家模型名称


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
    def from_env(cls, env_path: str = ".env") -> 'AppConfig':
        """从环境变量加载配置 (.env文件 + 系统环境变量)"""
        # 先加载 .env 文件
        load_env_file(env_path)
        
        # BSHT配置 - 处理空字符串情况
        def _get_int(env_key, default):
            val = os.getenv(env_key, str(default))
            try:
                return int(val) if val else default
            except ValueError:
                return default
        
        bsht = BSHTConfig(
            username=os.getenv("BSHT_USERNAME", ""),
            password=os.getenv("BSHT_PASSWORD", ""),
            channel_id=_get_int("BSHT_CHANNEL_ID", 0),
            channel_passcode=_get_int("BSHT_CHANNEL_PASSCODE", 0)
        )
        
        # API配置
        api = APIConfig(
            siliconflow_key=os.getenv("SILICONFLOW_API_KEY", ""),
            base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
            zhipu_key=os.getenv("ZHIPU_API_KEY", ""),
            zhipu_base_url=os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            expert_model_enabled=os.getenv("EXPERT_MODEL_ENABLED", "true").lower() == "true",
            expert_model=os.getenv("EXPERT_MODEL", "glm-4-flash")
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
            max_records=_get_int("DATABASE_MAX_RECORDS", 10000)
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
_env_path: str = ".env"


def get_config(env_path: str = ".env") -> AppConfig:
    """获取全局配置实例"""
    global _config, _env_path
    _env_path = env_path
    if _config is None:
        _config = AppConfig.from_env(env_path)
    return _config


def reload_config(env_path: str = None) -> AppConfig:
    """重新加载配置"""
    global _config, _env_path
    if env_path:
        _env_path = env_path
    _config = AppConfig.from_env(_env_path)
    return _config


def set_config(config: AppConfig):
    """设置全局配置"""
    global _config
    _config = config
