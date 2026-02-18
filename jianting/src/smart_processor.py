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
import numpy as np
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

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
    content: str
    content_normalized: str
    user_id: str
    signal_quality: str
    confidence: float
    error: str = ""


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
            
            # 噪声估计 (取能量最低的段落)
            frame_size = 960
            n_frames = len(audio) // frame_size
            energies = []
            for i in range(min(n_frames, 50)):
                frame = audio[i*frame_size:(i+1)*frame_size]
                energies.append(np.mean(frame ** 2))
            
            if energies:
                noise_floor = np.percentile(energies, 10)
                noise_db = 20 * np.log10(noise_floor + 1e-10)
                snr_db = rms_db - noise_db
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
    
    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1"):
        self.api_key = api_key
        self.base_url = base_url
    
    def call_asr(self, audio_path: str) -> Tuple[bool, str]:
        """调用ASR识别"""
        try:
            import requests
            
            url = f"{self.base_url}/audio/asr"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            with open(audio_path, 'rb') as f:
                files = {'file': ('audio.wav', f, 'audio/wav')}
                data = {'language': 'auto', 'format': 'wav'}
                response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "")
                return True, text
            else:
                return False, f"API错误: {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def call_expert_analysis(self, audio_path: str, asr_text: str) -> Tuple[bool, str]:
        """调用专家分析"""
        try:
            import requests
            
            # 读取音频文件为base64
            import base64
            with open(audio_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""你是一个业余无线电通信专家。请分析以下音频的识别结果：

识别文本: {asr_text}

请分析并返回JSON格式结果:
{{
    "signal_type": "CQ/QSO/NOISE/UNKNOWN",  // 信号类型
    "content_normalized": "规范化内容",       // 规范化后的内容
    "user_id": "呼号/工号",                   // 如果能识别
    "signal_quality": "1-9",                 // 信号质量
    "confidence": 0.0-1.0                    // 分析置信度
}}

只返回JSON，不要其他内容。"""
            
            payload = {
                "model": "Qwen/Qwen3-8B",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
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
        self.ai = AIClient(api_key)
        
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
            
            # 6. ASR识别
            success, asr_text = self.ai.call_asr(audio_to_use)
            if not success:
                return (
                    AIResult(success=False, signal_type="UNKNOWN", content=asr_text,
                            content_normalized="", user_id="", signal_quality="",
                            confidence=0.0, error=asr_text),
                    quality,
                    suggestion
                )
            
            # 7. 专家分析
            success, analysis = self.ai.call_expert_analysis(audio_to_use, asr_text)
            
            ai_result = AIResult(
                success=True,
                signal_type="UNKNOWN",
                content=asr_text,
                content_normalized=asr_text,
                user_id="",
                signal_quality="5",
                confidence=0.5
            )
            
            if success:
                try:
                    # 解析JSON
                    analysis_json = analysis.replace("```json", "").replace("```", "").strip()
                    data = json.loads(analysis_json)
                    
                    ai_result.signal_type = data.get("signal_type", "UNKNOWN")
                    ai_result.content_normalized = data.get("content_normalized", asr_text)
                    ai_result.user_id = data.get("user_id", "")
                    ai_result.signal_quality = data.get("signal_quality", "5")
                    ai_result.confidence = data.get("confidence", 0.5)
                except:
                    pass
            
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
