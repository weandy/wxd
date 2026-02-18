"""
智能音频处理模块 - 集成DSP和AI识别
高内聚低耦合设计

功能:
1. 音频质量分析 (SNR检测)
2. 智能DSP处理决策
3. AI语音识别 (ASR)
4. 专家分析 (Qwen3)
"""
import os
import sys
import json
import wave
import tempfile
import shutil
import threading
import logging
import time
import numpy as np
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from functools import wraps

# 使用日志配置模块
from logger_config import setup_logger
logger = setup_logger("SmartProcessor", "recognize")


def retry_on_error(max_attempts: int = 3, backoff: float = 1.0, 
                   retry_on_timeout: bool = True, retry_on_connection: bool = True):
    """
    API调用重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        backoff: 基础退避时间(秒)，使用指数退避
        retry_on_timeout: 是否对超时错误重试
        retry_on_connection: 是否对连接错误重试
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e).lower()
                    
                    # 判断是否可重试
                    should_retry = False
                    
                    # 超时错误
                    if retry_on_timeout and ('timeout' in error_str or 'timed out' in error_str):
                        should_retry = True
                    
                    # 连接错误
                    if retry_on_connection:
                        if any(x in error_str for x in ['connection', 'connection refused', 'connection reset', 
                                                        'network', '无法连接', '连接失败', '远程主机']):
                            should_retry = True
                    
                    # 5xx 服务器错误
                    if '500' in error_str or '502' in error_str or '503' in error_str or '504' in error_str:
                        should_retry = True
                    
                    # 429 速率限制
                    if '429' in error_str or 'rate limit' in error_str:
                        should_retry = True
                    
                    if not should_retry or attempt == max_attempts - 1:
                        logger.error(f"[{func.__name__}] 重试次数用尽: {e}")
                        raise
                    
                    # 指数退避
                    wait_time = backoff * (2 ** attempt)
                    logger.warning(f"[{func.__name__}] 失败，{wait_time:.1f}s后重试 ({attempt+1}/{max_attempts}): {e}")
                    time.sleep(wait_time)
            
            raise last_exception
        return wrapper
    return decorator

# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DSP_TEST_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "dsp_test")

# 添加DSP测试目录到路径
if DSP_TEST_DIR not in sys.path:
    sys.path.insert(0, DSP_TEST_DIR)


@dataclass
class AudioQuality:
    """音频质量指标"""
    rms_db: float
    peak_db: float
    noise_db: float
    snr_db: float
    dynamic_range_db: float
    sample_rate: int
    duration: float


@dataclass
class DSPSuggestion:
    """DSP处理建议"""
    needed: bool
    reason: str
    level: str  # LOW, MEDIUM, HIGH, VERY_HIGH
    algorithm: str
    confidence: float


@dataclass
class AIResult:
    """AI识别结果"""
    success: bool
    signal_type: str  # CQ, QSO, NOISE, UNKNOWN
    content: str  # SenseVoice原始识别结果
    content_normalized: str
    user_id: str
    signal_quality: str
    confidence: float
    error: str = ""
    sensevoice_content: str = ""  # SenseVoice原始结果
    expert_content: str = ""  # Qwen专家模型原始结果


class AudioQualityAnalyzer:
    """音频质量分析器"""
    
    @staticmethod
    def analyze(audio_path: str) -> Optional[AudioQuality]:
        """分析音频质量"""
        try:
            with wave.open(audio_path, 'rb') as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
            
            # 转换
            if params.sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = np.frombuffer(frames, dtype=np.float32)
            
            # 转单声道
            if params.nchannels > 1:
                audio = audio.reshape(-1, params.nchannels).mean(axis=1)
            
            # 计算指标
            rms = np.sqrt(np.mean(audio ** 2))
            rms_db = 20 * np.log10(rms + 1e-10)
            
            # 峰值
            peak = np.max(np.abs(audio))
            peak_db = 20 * np.log10(peak + 1e-10)
            
            # 噪声估计 - 使用整个音频分析，取能量最低的段落
            # 使用更小的帧来获得更准确的噪声估计
            frame_size = 480  # 10ms @ 48kHz
            n_frames = len(audio) // frame_size
            
            if n_frames < 10:
                # 音频太短，使用固定估算
                noise_db = -60
                snr_db = rms_db - noise_db
            else:
                # 计算所有帧的能量
                energies = []
                for i in range(n_frames):
                    frame = audio[i*frame_size:(i+1)*frame_size]
                    energies.append(np.mean(frame ** 2))
                
                energies = np.array(energies)
                
                # 取能量最低的20%作为噪声估计（更保守的估计）
                if len(energies) > 0:
                    noise_floor = np.percentile(energies, 20)
                    noise_db = 20 * np.log10(noise_floor + 1e-10)
                    snr_db = rms_db - noise_db
                    
                    # 防止异常值
                    if snr_db < 0:
                        snr_db = 0
                    elif snr_db > 80:  # 异常高可能是计算错误
                        snr_db = 80
                else:
                    noise_db = -60
                    snr_db = 0
            
            # 动态范围
            dynamic_range = peak_db - rms_db
            
            return AudioQuality(
                rms_db=rms_db,
                peak_db=peak_db,
                noise_db=noise_db,
                snr_db=snr_db,
                dynamic_range_db=dynamic_range,
                sample_rate=params.framerate,
                duration=len(audio) / params.framerate
            )
        except Exception as e:
            print(f"音频分析错误: {e}")
            return None
    
    @staticmethod
    def suggest_dsp(quality: AudioQuality, 
                   threshold_high: float = 20.0,
                   threshold_low: float = 10.0) -> DSPSuggestion:
        """根据音频质量建议DSP处理"""
        snr = quality.snr_db
        
        if snr > threshold_high:
            return DSPSuggestion(
                needed=False,
                reason=f"信噪比很高 ({snr:.1f}dB)，音频本身很清晰",
                level="LOW",
                algorithm="none",
                confidence=0.95
            )
        elif snr > threshold_low:
            return DSPSuggestion(
                needed=True,
                reason=f"信噪比中等 ({snr:.1f}dB)，DSP可能有轻微改善",
                level="MEDIUM",
                algorithm="timedomain",
                confidence=0.7
            )
        elif snr > 0:
            return DSPSuggestion(
                needed=True,
                reason=f"信噪比较低 ({snr:.1f}dB)，建议使用DSP降噪",
                level="HIGH",
                algorithm="spectral",
                confidence=0.85
            )
        else:
            return DSPSuggestion(
                needed=True,
                reason=f"信噪比很低 ({snr:.1f}dB)，强烈建议使用DSP降噪",
                level="VERY_HIGH",
                algorithm="rnnoise",
                confidence=0.9
            )


class DSPProcessor:
    """DSP处理器"""
    
    _chain = None
    _lock = threading.Lock()
    
    def __init__(self, algorithm: str = "timedomain", agc_mode: str = "webrtc"):
        self.algorithm = algorithm
        self.agc_mode = agc_mode
    
    def _get_chain(self):
        """获取DSP处理链 (延迟初始化)"""
        if DSPProcessor._chain is None:
            with DSPProcessor._lock:
                if DSPProcessor._chain is None:
                    try:
                        from dsp_chain import AudioDSPChain
                        DSPProcessor._chain = AudioDSPChain(
                            sample_rate=48000,
                            frame_size=960,
                            vad_enabled=False,
                            noise_reduction_algorithm=self.algorithm,
                            agc_mode=self.agc_mode
                        )
                    except Exception as e:
                        print(f"DSP链初始化失败: {e}")
                        return None
        return DSPProcessor._chain
    
    def process(self, input_path: str, output_path: str) -> Tuple[bool, str]:
        """处理音频文件"""
        chain = self._get_chain()
        if chain is None:
            return False, "DSP处理链未初始化"
        
        try:
            # 读取音频
            with wave.open(input_path, 'rb') as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
            
            if params.sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = np.frombuffer(frames, dtype=np.float32)
            
            if params.nchannels > 1:
                audio = audio.reshape(-1, params.nchannels).mean(axis=1)
            
            # 处理
            processed = chain.process_audio(audio)
            
            # 转换回16位
            processed = np.clip(processed, -1.0, 1.0)
            processed_int = (processed * 32767).astype(np.int16)
            
            # 写入
            with wave.open(output_path, 'wb') as wf:
                wf.setparams((1, 2, params.framerate, len(processed_int), 'NONE', ''))
                wf.writeframes(processed_int.tobytes())
            
            return True, "处理成功"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def convert_to_mono(input_path: str, output_path: str) -> bool:
        """转换为单声道"""
        try:
            with wave.open(input_path, 'rb') as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
            
            if params.sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = np.frombuffer(frames, dtype=np.float32)
            
            if params.nchannels > 1:
                audio = audio.reshape(-1, params.nchannels).mean(axis=1)
            
            audio_int = (audio * 32767).astype(np.int16)
            
            with wave.open(output_path, 'wb') as wf:
                wf.setparams((1, 2, params.framerate, len(audio_int), 'NONE', ''))
                wf.writeframes(audio_int.tobytes())
            
            return True
        except Exception as e:
            print(f"转换失败: {e}")
            return False


class AIClient:
    """AI识别客户端"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1", 
                 expert_model: str = "Qwen/Qwen2.5-7B-Instruct"):
        self.api_key = api_key
        self.base_url = base_url
        self.expert_model = expert_model
        self.prompts = self._load_prompts()
        self.prompt_md = self._load_prompt_md()  # 加载md格式的prompt
    
    def _load_prompts(self) -> Dict[str, Any]:
        """从配置文件加载prompt"""
        prompt_file = os.path.join(SCRIPT_DIR, "prompts.json")
        default_prompts = {
            "expert_analysis": {
                "system_prompt": "你是一个专业的业余无线电通信专家，精通HAM通联术语和字母解释法。",
                "user_prompt_template": "识别文本: {asr_text}\n\n请根据以上规则分析和规范化内容，只返回JSON，不要其他内容。",
                "output_format": {
                    "signal_type": "CQ/QSO/CQ73/QRZ/NOISE/UNKNOWN",
                    "content_normalized": "规范化后的完整通联内容，保留关键呼号",
                    "user_id": "提取的呼号或ID",
                    "signal_quality": "1-9",
                    "confidence": "0.0-1.0"
                }
            },
            "asr_prompt": "你是一个语音识别专家。请识别这段音频中的语音内容，直接输出识别到的文字，不要其他内容。"
        }
        
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    print(f"[AIClient] 已加载Prompt配置: {prompt_file}")
                    return loaded
        except Exception as e:
            print(f"[AIClient] 加载Prompt配置失败，使用默认: {e}")
        
        return default_prompts
    
    def _load_prompt_md(self) -> str:
        """从prompts.md加载prompt"""
        md_file = os.path.join(SCRIPT_DIR, "prompts.md")
        if os.path.exists(md_file):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print(f"[AIClient] 已加载Prompt MD: {md_file}")
                    return content
            except Exception as e:
                print(f"[AIClient] 加载Prompt MD失败: {e}")
        return ""
    
    @retry_on_error(max_attempts=3, backoff=2.0)
    def call_asr(self, audio_path: str) -> Tuple[bool, str]:
        """调用ASR识别 - 使用 SiliconFlow SenseVoice"""
        try:
            import requests
            
            # SiliconFlow ASR API 端点
            url = f"{self.base_url}/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            with open(audio_path, 'rb') as f:
                files = {
                    'file': ('audio.wav', f, 'audio/wav')
                }
                data = {
                    'model': 'FunAudioLLM/SenseVoiceSmall',
                    'language': 'zh',  # 强制中文识别
                    'response_format': 'json'
                }
                response = requests.post(url, files=files, data=data, headers=headers, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                # 处理不同的响应格式
                text = result.get("text", "") or result.get("data", {}).get("text", "")
                return True, text
            else:
                # 尝试另一种方式 - 使用 chat completions 方式的 ASR
                return self._call_asr_via_chat(audio_path)
        except Exception as e:
            # 备用方案
            return self._call_asr_via_chat(audio_path)
    @retry_on_error(max_attempts=3, backoff=2.0)
    def _call_asr_via_chat(self, audio_path: str) -> Tuple[bool, str]:
        """通过 chat 接口调用 ASR"""
        try:
            import requests
            import base64
            
            # 读取音频文件
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # 使用带有音频输入的模型
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 使用 SenseVoice 模型进行语音识别
            payload = {
                "model": "FunAudioLLM/SenseVoiceSmall",
                "messages": [
                    {
                        "role": "user", 
                        "content": [
                            {"type": "audio", "audio_url": {"url": "data:audio/wav;base64," + base64.b64encode(audio_data).decode()}},
                            {"type": "text", "text": "请识别这段音频中的中文语音内容，直接输出识别到的中文文字，不要其他内容。如果不是中文，请输出空。"}
                        ]
                    }
                ],
                "max_tokens": 1024
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, content
            else:
                return False, f"API错误: {response.status_code} - {response.text[:100]}"
        except Exception as e:
            return False, f"ASR错误: {str(e)}"
    @retry_on_error(max_attempts=3, backoff=2.0)
    def call_expert_analysis(self, audio_path: str, asr_text: str) -> Tuple[bool, str]:
        """调用专家分析 - 优先使用prompts.md"""
        try:
            import requests
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 优先使用prompts.md
            if self.prompt_md:
                prompt = f"""{self.prompt_md}

---

ASR识别结果: "{asr_text}"

请根据上述规则修正识别结果，只返回JSON格式:
{{"signal_type":"CQ/QSO/CQ73/QRZ/NOISE/UNKNOWN","content_normalized":"修正后的文本","user_id":"呼号","signal_quality":"1-9","confidence":0.0-1.0}}

只返回JSON。"""
            else:
                # 回退到prompts.json
                expert_config = self.prompts.get("expert_analysis", {})
                system_prompt = expert_config.get("system_prompt", "你是一个业余无线电通信专家。")
                correction_rules = expert_config.get("correction_rules", {})
                common_mistakes = correction_rules.get("common_mistakes", [])
                number_mappings = correction_rules.get("number_mappings", {})
                
                corrections_text = "\n".join([f'"{m["from"]}" → "{m["to"]}"' for m in common_mistakes[:10]])
                numbers_text = ", ".join([f'"{k}"={v}' for k,v in number_mappings.items()])
                
                user_template = expert_config.get("user_prompt_template", "ASR: {asr_text}")
                output_format = expert_config.get("output_format", {})
                
                prompt = f"""{system_prompt}

{corrections_text}

{numbers_text}

{user_template.format(asr_text)}

{json.dumps(output_format, ensure_ascii=False)}

只返回JSON，不要其他内容。"""
            
            # 使用配置的专家模型
            payload = {
                "model": self.expert_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, content
            else:
                return False, f"API错误: {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def call_expert_asr(self, audio_path: str) -> Tuple[bool, str]:
        """调用专家模型识别音频 - 使用Qwen模型直接识别语音"""
        try:
            import requests
            import base64
            
            # 读取音频文件
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 使用专家模型进行语音识别
            asr_prompt = self.prompts.get("asr_prompt", "你是HAM语音识别助手。请忽略背景噪音，尽力识别所有中文对话、字母和数字。直接输出文字，不要其他内容。")
            
            payload = {
                "model": self.expert_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "audio", "audio_url": {"url": "data:audio/wav;base64," + base64.b64encode(audio_data).decode()}},
                            {"type": "text", "text": asr_prompt}
                        ]
                    }
                ],
                "max_tokens": 1024
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, content
            else:
                return False, f"API错误: {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def call_final_analysis(self, audio_path: str, sensevoice_result: str, expert_result: str) -> Tuple[bool, str]:
        """最终综合分析 - 综合SenseVoice和专家模型的识别结果"""
        try:
            import requests
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 从加载的配置中获取prompt
            expert_config = self.prompts.get("expert_analysis", {})
            system_prompt = expert_config.get("system_prompt", "你是一个业余无线电通信专家。")
            
            # 获取纠正规则
            correction_rules = expert_config.get("correction_rules", {})
            common_mistakes = correction_rules.get("common_mistakes", [])
            number_mappings = correction_rules.get("number_mappings", {})
            
            # 构建纠正规则文本
            corrections_text = "\n".join([f'"{m["from"]}" → "{m["to"]}"' for m in common_mistakes[:10]])
            numbers_text = ", ".join([f'"{k}"={v}' for k,v in number_mappings.items()])
            
            output_format = expert_config.get("output_format", {})
            
            # 构建综合分析的prompt - 强制基于实际识别结果，禁止猜测
            # 如果两个识别结果相同，直接使用；如果不同，选择更合理的
            # 如果识别结果是无意义内容（如"测试测试"），应返回空内容
            prompt = f"""你是一个严格的业余无线电通信分析助手。

## 原始识别结果 (必须严格基于这些结果，禁止编造!):
- SenseVoice识别结果: "{sensevoice_result}"
- Qwen识别结果: "{expert_result}"

## 重要规则:
1. 如果两个识别结果相同，直接使用该结果
2. 如果两个结果不同，选择更通顺合理的那个
3. **禁止猜测**: 绝对不允许生成原始识别结果中没有的内容!
4. **无意义内容**: 如果识别结果是"测试测试"、"啊啊"、"嗯嗯"等无意义内容，必须返回空内容
5. 只进行必要的纠错(如"柴友"→"台友")，不要改变原始识别的内容

## 呼号格式:
- 中国呼号: 2-6位字母数字组合(如BG1ABC, BD1NA)
- 呼号必须来自上述识别结果，不能猜测

## 输出格式 (只返回JSON):
{json.dumps(output_format, ensure_ascii=False)}

严格遵守上述规则，只返回JSON。"""
            
            payload = {
                "model": self.expert_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, content
            else:
                return False, f"API错误: {response.status_code}"
        except Exception as e:
            return False, str(e)


class SmartAudioProcessor:
    """智能音频处理器 - 整合所有功能"""
    
    def __init__(self, api_key: str, dsp_config: Dict[str, Any] = None):
        self.api_key = api_key
        self.dsp_config = dsp_config or {}
        
        # 初始化组件
        self.analyzer = AudioQualityAnalyzer()
        self.dsp = DSPProcessor(
            algorithm=self.dsp_config.get("algorithm", "timedomain"),
            agc_mode=self.dsp_config.get("agc_mode", "webrtc")
        )
        
        # 专家模型配置
        expert_model = self.dsp_config.get("expert_model", "Qwen/Qwen2.5-7B-Instruct")
        self.ai = AIClient(api_key, expert_model=expert_model)
        
        # SNR阈值
        self.snr_threshold_high = self.dsp_config.get("snr_threshold_high", 20.0)
        self.snr_threshold_low = self.dsp_config.get("snr_threshold_low", 10.0)
    
    def process(self, audio_path: str, keep_temp: bool = False) -> Tuple[AIResult, AudioQuality, DSPSuggestion]:
        """
        智能处理音频
        
        Returns:
            (AIResult, AudioQuality, DSPSuggestion)
        """
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 1. 分析原始音频质量
            quality = self.analyzer.analyze(audio_path)
            if quality is None:
                return (
                    AIResult(success=False, signal_type="UNKNOWN", content="",
                            content_normalized="", user_id="", signal_quality="",
                            confidence=0.0, error="音频分析失败"),
                    AudioQuality(0, 0, 0, 0, 0, 0, 0),
                    DSPSuggestion(False, "", "LOW", "", 0)
                )
            
            # 2. 判断是否需要DSP
            suggestion = self.analyzer.suggest_dsp(
                quality, 
                self.snr_threshold_high,
                self.snr_threshold_low
            )
            
            # 3. 准备音频文件
            temp_original = os.path.join(temp_dir, "original.wav")
            temp_processed = os.path.join(temp_dir, "processed.wav")
            
            if not self.dsp.convert_to_mono(audio_path, temp_original):
                return (
                    AIResult(success=False, signal_type="UNKNOWN", content="",
                            content_normalized="", user_id="", signal_quality="",
                            confidence=0.0, error="音频转换失败"),
                    quality,
                    suggestion
                )
            
            # 4. DSP处理 (如果需要)
            use_processed = False
            if suggestion.needed:
                success, msg = self.dsp.process(temp_original, temp_processed)
                if success:
                    use_processed = True
            
            # 5. 选择要使用的音频
            audio_to_use = temp_processed if use_processed else temp_original
            
            # 6. 三级处理: SenseVoice + Qwen专家模型 + 综合分析
            
            # 6.1 SenseVoice ASR识别
            success, sensevoice_text = self.ai.call_asr(audio_to_use)
            if not success:
                return (
                    AIResult(success=False, signal_type="UNKNOWN", content=sensevoice_text,
                            content_normalized="", user_id="", signal_quality="",
                            confidence=0.0, error=sensevoice_text),
                    quality,
                    suggestion
                )
            
            # 6.2 Qwen专家模型识别 (二级处理)
            success, expert_text = self.ai.call_expert_asr(audio_to_use)
            if not success:
                # 如果专家模型识别失败，回退到只用SenseVoice
                expert_text = sensevoice_text
            
            # 6.3 最终综合分析 (三级处理)
            # 当两个识别结果相同且有效时，直接使用，跳过final_analysis
            sensevoice_clean = sensevoice_text.strip() if sensevoice_text else ""
            expert_clean = expert_text.strip() if expert_text else ""
            
            # 如果两个结果相同且有效，直接使用
            if sensevoice_clean and sensevoice_clean == expert_clean:
                analysis = f'{{"signal_type": "UNKNOWN", "content_normalized": "{sensevoice_clean}", "user_id": "", "signal_quality": "5", "confidence": 0.8}}'
                logger.info(f"[快速路径] 识别结果一致，直接使用: {sensevoice_clean[:30]}")
            else:
                # 结果不同，调用final_analysis综合分析
                success, analysis = self.ai.call_final_analysis(audio_to_use, sensevoice_text, expert_text)
                if not success:
                    analysis = ""
            
            # 记录原始识别结果
            asr_text = sensevoice_text
            expert_asr_text = expert_text
            
            ai_result = AIResult(
                success=True,
                signal_type="UNKNOWN",
                content=asr_text,
                content_normalized=asr_text,
                user_id="",
                signal_quality="5",
                confidence=0.5,
                sensevoice_content=sensevoice_text,
                expert_content=expert_text
            )
            
            if analysis:
                try:
                    # 解析JSON
                    analysis_json = analysis.replace("```json", "").replace("```", "").strip()
                    data = json.loads(analysis_json)
                    
                    # 只有当原始ASR有内容时才接受识别结果
                    normalized = data.get("content_normalized", "")
                    if normalized and normalized.strip():
                        ai_result.signal_type = data.get("signal_type", "UNKNOWN")
                        ai_result.content_normalized = normalized
                        ai_result.user_id = data.get("user_id", "")
                        ai_result.signal_quality = data.get("signal_quality", "5")
                        ai_result.confidence = data.get("confidence", 0.5)
                    else:
                        # ASR没有识别到内容，标记失败
                        ai_result.success = False
                        ai_result.error = "ASR未识别到内容"
                except:
                    # JSON解析失败，标记失败
                    ai_result.success = False
                    ai_result.error = "响应解析失败"
            
            # 8. 分析处理后质量
            if use_processed:
                proc_quality = self.analyzer.analyze(temp_processed)
                if proc_quality:
                    suggestion = DSPSuggestion(
                        needed=suggestion.needed,
                        reason=f"处理前SNR: {quality.snr_db:.1f}dB, 处理后SNR: {proc_quality.snr_db:.1f}dB",
                        level=suggestion.level,
                        algorithm=suggestion.algorithm,
                        confidence=suggestion.confidence
                    )
            
            return ai_result, quality, suggestion
            
        finally:
            # 清理临时文件
            if not keep_temp:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
