"""
智能音频处理模块 - 集成AI识别
高内聚低耦合设计

功能:
1. 音频质量分析 (SNR检测)
2. AI语音识别 (ASR)
3. 专家分析 (Qwen3)
"""
import os
import json
import wave
import shutil
import logging
import time
import numpy as np
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from functools import wraps

# 延迟导入日志配置，避免相对导入问题
def _get_logger():
    try:
        from .logging_setup import setup_logger
        return setup_logger("SmartProcessor", "recognize")
    except ImportError:
        # 回退到标准logging
        return logging.getLogger("SmartProcessor")

logger = _get_logger()


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


class AIClient:
    """AI识别客户端"""

    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.prompts = self._load_prompts()
        self.prompt_md = self._load_prompt_md()  # 加载md格式的prompt
    
    def _load_prompts(self) -> Dict[str, Any]:
        """从配置文件加载prompt - 只使用prompts.md"""
        # prompts.json 已弃用，只保留 prompts.md
        # 保留此方法以兼容旧代码，返回空字典
        return {}
    
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

    def _load_correction_rules(self) -> dict:
        """从数据库加载纠错规则"""
        try:
            from web.models.database import get_db_path
            import sqlite3
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT wrong_text, correct_text
                FROM correction_rules
                WHERE enabled = 1
                ORDER BY priority DESC
            """)
            rules = {row['wrong_text']: row['correct_text'] for row in cursor.fetchall()}
            conn.close()
            if rules:
                print(f"[AIClient] 从数据库加载 {len(rules)} 条纠错规则")
            return rules
        except Exception as e:
            # 数据库不可用时返回空字典，使用内置规则
            return {}

    def _apply_correction_rules(self, text: str) -> str:
        """应用本地纠错规则"""
        if not text:
            return text

        import re

        # 优先从数据库加载纠错规则
        rules = self._load_correction_rules()

        # 如果数据库有规则，使用数据库规则
        if rules:
            corrections = rules
        else:
            # 备用：使用内置规则
            corrections = {
                # 高频错误
                '柴友': '台友',
                '财友': '台友',
                '菜油': '台友',
                '超收': '抄收',
                '抄手': '抄收',
                '有他': '有台',
                '抽书': '抄收',
                # 常见误识别
                '抄收': '抄收',
                '台有': '台友',
                '台优': '台友',
                '台由': '台友',
                '台柚': '台友',
                '太友': '台友',
                '套友': '台友',
                # 数字相关
                '幺': '1',
                '腰': '1',
                '两': '2',
                '二': '2',
                '三': '3',
                '山': '3',
                '思': '4',
                '四': '4',
                '无': '5',
                '五': '5',
                '陆': '6',
                '量': '6',
                '大': '6',
                '拐': '7',
                '起': '7',
                '七': '7',
                '九': '9',
                '狗': '9',
                '动': '0',
                '洞': '0',
                '栋': '0',
                # 字母解释法相关
                'sQ': 'CQ',
                'sQCQ': 'CQ',
                'cQ': 'CQ',
                'CQ CQ CQ CQ': 'CQ CQ CQ',
            }

        result = text

        # 应用词语纠错
        for wrong, correct in corrections.items():
            result = result.replace(wrong, correct)
        
        # 清理呼号后面的多余字符 - 只保留5-6位呼号
        # 如 BD6KFPbdtas -> BD6KFP
        def clean_callsign(m):
            call = m.group(0)
            # 保留前5-6位
            return call[:6]
        
        result = re.sub(r'[A-Z]{1,2}\d{1,2}[A-Z0-9]{4,10}', clean_callsign, result, flags=re.IGNORECASE)
        
        # 清理重复的单词（如 kilolo → Kilo）
        result = re.sub(r'(Kilo)\1+', r'\1', result)
        
        return result
    
    def _extract_callsign(self, text: str) -> str:
        """提取呼号 - 5-6位字母数字混合"""
        if not text:
            return ""
        
        import re
        
        # 匹配5-6位的字母数字混合（以字母开头，后面包含数字）
        # 不使用\b，允许在中文环境中匹配
        pattern = r'([A-Z]{1,2}\d{1,2}[A-Z0-9]{1,4})'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            # 转换为大写，取第一个匹配
            callsign = matches[0].upper()
            # 限制长度为6位
            if len(callsign) > 6:
                callsign = callsign[:6]
            return callsign
        
        return ""
    
    def _detect_signal_type(self, text: str) -> str:
        """判断信号类型"""
        import re
        
        if not text:
            return "UNKNOWN"
        
        text_upper = text.upper()
        
        # CQ呼叫
        if 'CQ' in text_upper:
            return "CQ"
        
        # 73祝福
        if '73' in text_upper:
            return "CQ73"
        
        # QRZ询问
        if 'QRZ' in text_upper:
            return "QRZ"
        
        # 信号报告 (59, 57等)
        if re.search(r'[34556789]\s*[123456789]', text_upper):
            return "QSO"
        
        # 双向对话关键词
        qso_keywords = ['抄收', '收到', '信号', '报告', '59', '57', '73', '谢谢', '再会']
        if any(kw in text_upper for kw in qso_keywords):
            return "QSO"
        
        return "UNKNOWN"
    
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
                logger.info(f"[SenseVoice] API返回200, 完整结果: {result}")

                # 打印响应文本的原始内容
                logger.info(f"[SenseVoice] 响应文本长度: {len(response.text)}")

                # 处理不同的响应格式
                text = result.get("text", "") or result.get("data", {}).get("text", "")
                if not text:
                    # 尝试其他可能的字段
                    text = result.get("result", {}).get("text", "") if isinstance(result.get("result"), dict) else ""
                if not text:
                    # 可能是直接返回文本
                    text = result.get("content", "") or result.get("transcription", "")

                logger.info(f"[SenseVoice] 提取的文本: '{text}'")

                # 如果文本为空，返回失败（音频无法识别）
                if not text:
                    logger.warning(f"[SenseVoice] ⚠️ 音频无法识别（无语音内容）")
                    return False, "语音识别失败：音频中无有效语音内容"

                return True, text
            elif response.status_code == 401:
                logger.error(f"[SenseVoice] ❌ API认证失败! 请检查 SILICONFLOW_API_KEY 是否正确或已过期")
                return False, "API认证失败，请检查 API Key"
            else:
                logger.warning(f"[SenseVoice] ⚠️ API返回 {response.status_code}")
                logger.warning(f"[SenseVoice] 响应内容: {response.text[:500]}")
                return False, f"API错误: {response.status_code}"
        except Exception as e:
            logger.warning(f"[SenseVoice] ⚠️ 异常: {type(e).__name__}: {e}")
            import traceback
            logger.warning(f"[SenseVoice] 堆栈: {traceback.format_exc()[:500]}")
            return False, f"识别异常: {str(e)}"
    @retry_on_error(max_attempts=3, backoff=2.0)
    def _call_asr_via_chat(self, audio_path: str) -> Tuple[bool, str]:
        """通过 chat 接口调用 ASR"""
        try:
            import requests
            import base64

            # 读取音频文件
            with open(audio_path, 'rb') as f:
                audio_data = f.read()

            logger.info(f"[SenseVoice] 尝试 chat 方式... (音频大小: {len(audio_data)} bytes)")

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
                logger.info(f"[SenseVoice] chat 方式成功: {content[:100] if content else '(空)'}")
                return True, content
            else:
                logger.warning(f"[SenseVoice] chat 方式失败: {response.status_code} - {response.text[:200]}")
                return False, f"API错误: {response.status_code} - {response.text[:100]}"
        except Exception as e:
            logger.warning(f"[SenseVoice] chat 方式异常: {e}")
            return False, f"ASR错误: {str(e)}"
    
    @retry_on_error(max_attempts=3, backoff=2.0)
    def call_tele_asr(self, audio_path: str) -> Tuple[bool, str]:
        """调用TeleSpeechASR - 并行ASR识别"""
        try:
            import requests
            
            # TeleSpeechASR API 端点
            url = f"{self.base_url}/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            with open(audio_path, 'rb') as f:
                files = {
                    'file': ('audio.wav', f, 'audio/wav')
                }
                data = {
                    'model': 'TeleAI/TeleSpeechASR',
                    'language': 'zh',
                    'response_format': 'json'
                }
                response = requests.post(url, files=files, data=data, headers=headers, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "") or result.get("data", {}).get("text", "")
                return True, text
            else:
                return False, f"TeleASR API错误: {response.status_code} - {response.text[:100]}"
        except Exception as e:
            return False, f"TeleASR错误: {str(e)}"
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
                "model": model_name,
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
        """最终综合分析 - 综合SenseVoice和TeleASR的识别结果"""
        try:
            import requests
            
            # 始终使用SiliconFlow API
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 优先使用prompts.md的完整内容
            prompt_md = getattr(self, 'prompt_md', '')
            
            # 构建prompt - 直接使用prompts.md的规则
            if prompt_md:
                # prompts.md已经包含了完整的规则，直接使用
                prompt = f"""{prompt_md}

---

## 待处理的语音识别结果:
"{sensevoice_result}"

请根据上述规则对这个语音识别结果进行转文字整理，并输出JSON格式的结果。"""
            else:
                prompt = f"""你是一个业余无线电通联语音转文字整理助手。

## 待处理内容:
"{sensevoice_result}"

## 你的任务:
1. 规范化呼号: BD6开→BD6KFP, 数字0和字母O纠错
2. 词语纠错: 糖友/柴友→台友, 抄手→抄收
3. 数字映射: 洞→0, 幺→1, 拐→7
4. 提取呼号和信号类型 (CQ/QSO/CQ73/UNKNOWN)
5. 完整保留原始内容

## 输出JSON:
{{"signal_type":"CQ/QSO/CQ73/UNKNOWN","content_normalized":"完整保留的规范化文本","user_id":"呼号","signal_quality":"1-9","confidence":0.0-1.0}}"""
            
            def call_model(model_name):
                """调用单个模型"""
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512
                }
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=120)
                    if response.status_code == 200:
                        result = response.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        return model_name, True, content
                    else:
                        return model_name, False, f"API错误: {response.status_code}"
                except Exception as e:
                    return model_name, False, str(e)
            
            # 只运行一个模型
            model_name = "THUDM/glm-4-9b-chat"
            
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=120)
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return True, content
                else:
                    return False, f"API错误: {response.status_code}"
            except Exception as e:
                return False, str(e)
            
            # 构建综合分析的prompt - 综合两个ASR结果进行文本分析
            if prompt_md:
                # 使用prompts.md的完整规则
                prompt = f"""{prompt_md}

---

## 两个ASR模型的识别结果:
- SenseVoice: "{sensevoice_result}"
- TeleASR: "{expert_result}"

## 任务要求 (必须执行):
1. **对比分析**: 比较两个ASR结果，选择更准确的版本，或者结合两者的优点
2. **应用纠错规则**: 
   - 字母解释法: Alpha→A, Bravo→B, Charlie→C...
   - 词语纠错: 柴友→台友, 抄手→抄收, 那个→那个...
   - 数字映射: 洞→0, 幺→1, 两→2, 3→三...
3. **判断信号类型**: CQ(普遍呼叫), QSO(双向通联), CQ73(结束祝福), QRZ(呼叫对方), NOISE(噪音), UNKNOWN(未知)
4. **提取呼号**: 找出HAM呼号

## 输出JSON:
{{"signal_type":"CQ/QSO/CQ73/QRZ/NOISE/UNKNOWN","content_normalized":"经过对比分析和纠错后的规范化文本","user_id":"提取的呼号","signal_quality":"1-9","confidence":0.0-1.0}}"""
            else:
                # 回退到prompts.json
                expert_config = self.prompts.get("expert_analysis", {})
                system_prompt = expert_config.get("system_prompt", "你是一个业余无线电通信专家。")
                correction_rules = expert_config.get("correction_rules", {})
                common_mistakes = correction_rules.get("common_mistakes", [])
                number_mappings = correction_rules.get("number_mappings", {})
                
                corrections_text = "\n".join([f'"{m["from"]}" → "{m["to"]}"' for m in common_mistakes[:15]])
                numbers_text = ", ".join([f'"{k}"={v}' for k,v in number_mappings.items()])
                
                output_format = expert_config.get("output_format", {})
                
                prompt = f"""你是一个严格的业余无线电通信分析助手。

## 两个ASR模型的识别结果:
- SenseVoice: "{sensevoice_result}"  
- TeleASR: "{expert_result}"

## 任务要求 (必须执行):
1. 对比两个ASR结果，选择更准确的版本或结合两者优点
2. 应用纠错规则:
   - 字母解释法: Alpha→A, Bravo→B, Charlie→C...
   - 词语纠错: 柴友→台友, 抄手→抄收, 那个→那个...
   - 数字映射: 洞→0, 幺→1, 两→2...
3. 判断信号类型: CQ/QSO/CQ73/QRZ/NOISE/UNKNOWN
4. 提取呼号

## 纠正规则:
{corrections_text}

## 数字映射:
{numbers_text}

## 输出格式:
{json.dumps(output_format, ensure_ascii=False)}"""
            
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

    async def chat_async(self, prompt: str, model: str = None) -> Tuple[bool, str]:
        """
        异步版本的 chat 方法 - 使用 httpx

        Args:
            prompt: 提示词
            model: 模型名称，默认使用 expert_model

        Returns:
            (成功标志, 结果内容)
        """
        try:
            import httpx

            model = model or self.expert_model
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)

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

    def __init__(self, api_key: str):
        self.api_key = api_key
        # 初始化组件
        self.analyzer = AudioQualityAnalyzer()
        # AI 客户端
        self.ai = AIClient(api_key)

    def process(self, audio_path: str) -> Tuple[AIResult, AudioQuality]:
        """
        智能处理音频

        Returns:
            (AIResult, AudioQuality)
        """
        # 1. 分析原始音频质量
        quality = self.analyzer.analyze(audio_path)
        if quality is None:
            return (
                AIResult(success=False, signal_type="UNKNOWN", content="",
                        content_normalized="", user_id="", signal_quality="",
                        confidence=0.0, error="音频分析失败"),
                AudioQuality(0, 0, 0, 0, 0, 0, 0)
            )

        # 2. 使用SenseVoice进行语音识别
        logger.info("[识别] 调用 SenseVoice 语音识别...")

        sensevoice_success, sensevoice_text = self.ai.call_asr(audio_path)
        if sensevoice_success and sensevoice_text:
            logger.info(f"[识别] SenseVoice结果: {sensevoice_text[:100]}...")
        else:
            logger.warning(f"[识别] SenseVoice失败: {sensevoice_text}")
            return (
                AIResult(success=False, signal_type="UNKNOWN", content="",
                        content_normalized="", user_id="", signal_quality="",
                        confidence=0.0, error="语音识别失败"),
                quality
            )

        # 3. 本地规则纠错
        logger.info("[识别] 应用本地规则纠错...")

        corrected_text = self.ai._apply_correction_rules(sensevoice_text)

        # 提取呼号
        user_id = self.ai._extract_callsign(corrected_text)

        # 判断信号类型
        signal_type = self.ai._detect_signal_type(corrected_text)

        # 使用纠错后的文本
        ai_result = AIResult(
            success=True,
            signal_type=signal_type,
            content=sensevoice_text,
            content_normalized=corrected_text,
            user_id=user_id,
            signal_quality="5",
            confidence=0.5,
            sensevoice_content=sensevoice_text,
            expert_content=""
        )

        return ai_result, quality
