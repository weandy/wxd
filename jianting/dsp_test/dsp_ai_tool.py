"""
DSP + AI 识别整合工具
功能: 本地DSP降噪 -> 云端AI识别 -> 结构化输出
特点: 
  - 保留原始录音文件
  - 云端ASR使用降噪后音频
  - 处理完成后删除降噪临时文件
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import threading
import json
import base64
import wave
import pyaudio
import requests
import numpy as np
import sys

# 添加DSP模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dsp_chain import AudioDSPChain
from agc import AGCProcessor

# ================= 配置区域 =================
# SiliconFlow API (需要替换为你的KEY)
API_KEY = "sk-grfgzzbhvatgwrdmdnqyxatbfyctrqmnmuhukrrhxusofidj"  # 替换为你的API Key
ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
CHAT_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 专家级 System Prompt (对讲机/HAM radio场景优化)
EXPERT_SYSTEM_PROMPT = """
# Role
你是一名资深的无线电通信（对讲机/公网对讲）信号分析专家。

# Task
你将收到一段【音频】和【ASR参考文本】。请分析通联内容并输出结构化数据。

# Analysis Rules
1. **去伪存真**: ASR常有同音错误，请依据音频发音修正文本。
2. **场景识别**:
   - **CQ**: 广泛呼叫
   - **QSO**: 双方通联/应答
   - **DISPATCH**: 调度指令/指挥调度
   - **REPORT**: 报告/汇报
   - **CHAT**: 闲聊
   - **NOISE**: 纯噪音/无效信号
3. **数据标准化**:
   - 工号/呼号: 提取并大写 (如 2032060101)
   - 音量/信号: 将口语转化为数字 (如 "满"->5, "小"->2)
   - 位置: 提取地点信息

# Output Format (JSON Only)
{
    "signal_type": "CQ / QSO / DISPATCH / REPORT / CHAT / NOISE",
    "content_normalized": "修正后的规范内容",
    "user_id": "工号/呼号 (String / null)",
    "signal_quality": "信号质量 1-5 (String / null)",
    "location": "位置/区域 (String / null)",
    "action": "动作/指令 (String / null)",
    "noise_level": "LOW / MEDIUM / HIGH",
    "confidence": 0.0-1.0,
    "reason": "判断依据"
}
"""

# ================= 音频处理模块 =================
class AudioProcessor:
    """本地DSP音频处理器"""
    
    @staticmethod
    def process_audio(input_path, output_path, algorithm="timedomain", agc_mode="enhanced"):
        """
        处理音频 - 降噪 + AGC
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            algorithm: 降噪算法
            agc_mode: AGC模式
            
        Returns:
            (成功标志, 消息)
        """
        try:
            # 加载音频
            with wave.open(input_path, 'rb') as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
            
            # 转换为numpy
            if params.sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = np.frombuffer(frames, dtype=np.float32)
            
            # 转单声道
            if params.nchannels > 1:
                audio = audio.reshape(-1, params.nchannels).mean(axis=1)
            
            sample_rate = params.framerate
            
            # DSP处理链
            chain = AudioDSPChain(
                sample_rate=sample_rate,
                frame_size=960,
                vad_enabled=False,
                noise_reduction_algorithm=algorithm,
                agc_mode=agc_mode
            )
            
            # 处理
            processed = chain.process_audio(audio)
            
            # 保存
            audio_int16 = (processed * 32768).astype(np.int16)
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())
            
            return True, f"处理完成"
            
        except Exception as e:
            return False, f"处理失败: {str(e)}"
    
    @staticmethod
    def convert_to_mono(input_path, output_path):
        """转换为API友好的单声道格式"""
        try:
            with wave.open(input_path, 'rb') as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
            
            if params.sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = np.frombuffer(frames, dtype=np.float32)
            
            # 转单声道
            if params.nchannels > 1:
                audio = audio.reshape(-1, params.nchannels).mean(axis=1)
            
            audio_int16 = (audio * 32768).astype(np.int16)
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(params.framerate)
                wf.writeframes(audio_int16.tobytes())
            
            return True
        except Exception as e:
            print(f"转换失败: {e}")
            return False


# ================= AI API 客户端 =================
class AIClient:
    """AI识别客户端"""
    
    @staticmethod
    def _file_to_base64(file_path):
        with open(file_path, "rb") as f:
            return f"data:audio/wav;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    
    @staticmethod
    def call_asr(file_path, lang="zh"):
        """调用SenseVoice进行语音转文字"""
        try:
            files = {"file": open(file_path, "rb")}
            payload = {
                "model": "FunAudioLLM/SenseVoiceSmall",
                "language": lang,
                "disable_disfluencies": "true"
            }
            headers = {"Authorization": f"Bearer {API_KEY}"}
            
            resp = requests.post(ASR_URL, data=payload, files=files, headers=headers, timeout=60)
            
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("text", "").strip()
                return True, text
            else:
                return False, f"API错误: {resp.status_code}"
                
        except Exception as e:
            return False, f"请求失败: {str(e)}"
    
    @staticmethod
    def call_expert_analysis(file_path, ref_text):
        """调用Qwen3进行专家分析"""
        try:
            audio_url = AIClient._file_to_base64(file_path)
            
            user_prompt = f"""
【ASR参考文本】: "{ref_text}"

请分析这段对讲机/无线电通话音频：
1. 只有当确实全是噪音/无声时，才标记为 NOISE。
2. 如果是人声对话（即使没有呼号），也是有效信号。
3. 请修正参考文本中的听写错误，特别注意数字和字母。
4. 如果是调度/指挥场景，注意提取指令内容。

请输出JSON格式的結構化分析结果。
"""

            payload = {
                "model": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
                "messages": [
                    {"role": "system", "content": EXPERT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "audio_url", "audio_url": {"url": audio_url}}
                        ]
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.1
            }
            headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
            
            resp = requests.post(CHAT_URL, json=payload, headers=headers, timeout=120)
            
            if resp.status_code == 200:
                result = resp.json()
                content = result['choices'][0]['message']['content']
                # 清理JSON格式
                content = content.replace("```json", "").replace("```", "").strip()
                return True, content
            else:
                return False, f"API错误: {resp.status_code}"
                
        except Exception as e:
            return False, f"请求失败: {str(e)}"


# ================= 音频播放器 =================
class AudioPlayer:
    """音频播放器"""
    
    def __init__(self):
        self.is_playing = False
        self.thread = None
    
    def play(self, file_path):
        if self.is_playing:
            self.stop()
        
        self.thread = threading.Thread(target=self._play, args=(file_path,), daemon=True)
        self.thread.start()
    
    def _play(self, file_path):
        try:
            pa = pyaudio.PyAudio()
            wf = wave.open(file_path, 'rb')
            
            stream = pa.open(
                format=pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            
            self.is_playing = True
            data = wf.readframes(1024)
            
            while data and self.is_playing:
                stream.write(data)
                data = wf.readframes(1024)
            
            stream.stop_stream()
            stream.close()
            pa.terminate()
            
        except Exception as e:
            print(f"播放错误: {e}")
        
        self.is_playing = False
    
    def stop(self):
        self.is_playing = False


# ================= 主界面 =================
class DSPAITool:
    """DSP + AI 整合工具"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("DSP + AI 智能分析台")
        self.root.geometry("950x850")
        
        # 状态
        self.player = AudioPlayer()
        self.input_file = None
        self.processed_file = "temp_dsp_processed.wav"
        self.upload_file = "temp_upload.wav"
        
        # 初始化UI
        self._init_ui()
    
    def _init_ui(self):
        # ===== 文件选择区 =====
        file_frame = ttk.LabelFrame(self.root, text="1. 文件选择", padding=10)
        file_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(file_frame, text="📁 选择音频文件", command=self.load_file).pack(side=tk.LEFT)
        self.lbl_file = ttk.Label(file_frame, text="未选择文件", foreground="blue")
        self.lbl_file.pack(side=tk.LEFT, padx=10)
        
        # ===== DSP设置区 =====
        dsp_frame = ttk.LabelFrame(self.root, text="2. DSP降噪设置", padding=10)
        dsp_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 降噪算法
        ttk.Label(dsp_frame, text="降噪算法:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.nr_algorithm = tk.StringVar(value="timedomain")
        nr_combo = ttk.Combobox(
            dsp_frame, 
            textvariable=self.nr_algorithm,
            values=["timedomain", "spectral", "wiener", "noisereduce"],
            state="readonly", width=15
        )
        nr_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # AGC模式
        ttk.Label(dsp_frame, text="AGC模式:").grid(row=0, column=2, sticky=tk.W, padx=15)
        self.agc_mode = tk.StringVar(value="enhanced")
        agc_combo = ttk.Combobox(
            dsp_frame,
            textvariable=self.agc_mode,
            values=["none", "simple", "webrtc", "enhanced"],
            state="readonly", width=15
        )
        agc_combo.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # 提示
        ttk.Label(
            dsp_frame, 
            text="*原始文件将保留，只上传处理后的音频用于AI识别",
            foreground="gray", font=("微软雅黑", 8)
        ).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        # ===== 播放控制 =====
        play_frame = ttk.Frame(self.root, padding=5)
        play_frame.pack(fill=tk.X, padx=10)
        
        self.btn_play = ttk.Button(
            play_frame, 
            text="▶ 播放原始音频", 
            state=tk.DISABLED,
            command=lambda: self.player.play(self.input_file)
        )
        self.btn_play.pack(side=tk.LEFT, padx=5)
        
        self.btn_play_processed = ttk.Button(
            play_frame,
            text="▶ 播放处理后音频",
            state=tk.DISABLED,
            command=lambda: self.player.play(self.processed_file)
        )
        self.btn_play_processed.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(play_frame, text="■ 停止", command=self.player.stop).pack(side=tk.LEFT, padx=5)
        
        # ===== 分析控制 =====
        analysis_frame = ttk.LabelFrame(self.root, text="3. AI 分析", padding=10)
        analysis_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_run = ttk.Button(
            analysis_frame,
            text="🚀 DSP+AI分析",
            command=self.run_analysis,
            state=tk.DISABLED
        )
        self.btn_run.pack(side=tk.LEFT, padx=5)
        
        self.btn_compare = ttk.Button(
            analysis_frame,
            text="🔄 对比分析",
            command=self.run_compare,
            state=tk.DISABLED
        )
        self.btn_compare.pack(side=tk.LEFT, padx=5)
        
        self.btn_smart = ttk.Button(
            analysis_frame,
            text="🧠 智能分析",
            command=self.run_smart_analysis,
            state=tk.DISABLED
        )
        self.btn_smart.pack(side=tk.LEFT)
        
        self.lbl_status = ttk.Label(analysis_frame, text="就绪", foreground="gray")
        self.lbl_status.pack(side=tk.LEFT, padx=10)
        
        # ===== 结果显示 =====
        result_frame = ttk.LabelFrame(self.root, text="4. 分析结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.txt_log = scrolledtext.ScrolledText(
            result_frame,
            height=20,
            font=("微软雅黑", 10)
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        # 配置标签样式
        self.txt_log.tag_config("step", foreground="gray")
        self.txt_log.tag_config("info", foreground="blue")
        self.txt_log.tag_config("success", foreground="green", font=("微软雅黑", 10, "bold"))
        self.txt_log.tag_config("error", foreground="red")
        self.txt_log.tag_config("warn", foreground="orange")
        
        # 底部说明
        bottom = ttk.Label(
            self.root,
            text="处理流程: 原始音频 → DSP降噪 → 临时文件 → 云端ASR → 删除临时 → 输出结果",
            foreground="gray", font=("微软雅黑", 8)
        )
        bottom.pack(pady=5)
    
    def log(self, text, tag=None):
        self.txt_log.insert(tk.END, text + "\n", tag)
        self.txt_log.see(tk.END)
    
    def load_file(self):
        f = filedialog.askopenfilename(
            filetypes=[("WAV音频", "*.wav"), ("所有文件", "*.*")]
        )
        if f:
            self.input_file = f
            self.lbl_file.config(text=os.path.basename(f))
            self.btn_play.config(state=tk.NORMAL)
            self.btn_run.config(state=tk.NORMAL)
            self.btn_compare.config(state=tk.NORMAL)
            self.btn_smart.config(state=tk.NORMAL)
            self.txt_log.delete(1.0, tk.END)
            self.log("已加载文件，可播放原始音频或开始分析", "info")
            self.log("「智能分析」会自动判断是否需要DSP处理并选择最佳方案", "info")
    
    def run_analysis(self):
        if not self.input_file:
            return
        
        self.btn_run.config(state=tk.DISABLED)
        self.txt_log.delete(1.0, tk.END)
        
        # 启动处理线程
        threading.Thread(target=self._process_pipeline, daemon=True).start()
    
    def _process_pipeline(self):
        """处理流水线"""
        try:
            # ===== Step 1: DSP降噪 =====
            self.root.after(0, lambda: self.lbl_status.config(text="DSP降噪中..."))
            self.log("➤ 步骤1: DSP降噪处理", "step")
            
            success, msg = AudioProcessor.process_audio(
                self.input_file,
                self.processed_file,
                algorithm=self.nr_algorithm.get(),
                agc_mode=self.agc_mode.get()
            )
            
            if not success:
                self.log(f"❌ DSP处理失败: {msg}", "error")
                self.root.after(0, lambda: self.lbl_status.config(text="DSP失败"))
                return
            
            self.log(f"   ✓ DSP处理完成", "step")
            self.root.after(0, lambda: self.btn_play_processed.config(state=tk.NORMAL))
            
            # ===== Step 2: 格式转换 =====
            self.root.after(0, lambda: self.lbl_status.config(text="格式转换..."))
            self.log("➤ 步骤2: 转换为API格式", "step")
            
            if not AudioProcessor.convert_to_mono(self.processed_file, self.upload_file):
                self.log("❌ 格式转换失败", "error")
                return
            
            self.log("   ✓ 格式转换完成", "step")
            
            # ===== Step 3: SenseVoice ASR =====
            self.root.after(0, lambda: self.lbl_status.config(text="语音识别中..."))
            self.log("➤ 步骤3: SenseVoice 语音转文字", "step")
            
            success, ref_text = AIClient.call_asr(self.upload_file)
            
            if not success:
                self.log(f"❌ ASR失败: {ref_text}", "error")
                self.root.after(0, lambda: self.lbl_status.config(text="ASR失败"))
                return
            
            if not ref_text or len(ref_text.strip()) < 1:
                self.log("🛑 无有效语音信号", "warn")
                self.root.after(0, lambda: self.lbl_status.config(text="静音"))
                return
            
            self.log(f"   参考文本: {ref_text}", "step")
            
            # ===== Step 4: Qwen3 专家分析 =====
            self.root.after(0, lambda: self.lbl_status.config(text="AI分析中..."))
            self.log("➤ 步骤4: Qwen3 专家分析", "step")
            
            success, result_str = AIClient.call_expert_analysis(self.upload_file, ref_text)
            
            if not success:
                self.log(f"❌ 分析失败: {result_str}", "error")
                return
            
            # 解析JSON结果
            try:
                result = json.loads(result_str)
                self._display_result(result)
            except:
                self.log(f"解析失败: {result_str}", "warn")
            
            # ===== Step 5: 清理临时文件 =====
            self.log("➤ 步骤5: 清理临时文件", "step")
            
            # 删除处理后的临时文件
            for temp_file in [self.processed_file, self.upload_file]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        self.log(f"   ✓ 已删除: {temp_file}", "step")
                except:
                    pass
            
            self.log("   ✓ 临时文件清理完成", "step")
            self.root.after(0, lambda: self.lbl_status.config(text="完成"))
            
        except Exception as e:
            self.log(f"❌ 错误: {str(e)}", "error")
            self.root.after(0, lambda: self.lbl_status.config(text="错误"))
        
        finally:
            self.root.after(0, lambda: self.btn_run.config(state=tk.NORMAL))
    
    def _display_result(self, result):
        """显示分析结果"""
        self.log("\n" + "=" * 50, "step")
        
        sig_type = result.get("signal_type", "UNKNOWN")
        
        if sig_type == "NOISE":
            self.log(f"🚫 判定: 噪音/无效信号", "error")
        else:
            self.log(f"✅ 判定: {sig_type} (有效信号)", "success")
        
        # 噪声等级
        nl = result.get("noise_level", "UNKNOWN")
        if nl == "HIGH":
            self.log(f"   ⚠️ 底噪较高，结果仅供参考", "warn")
        
        # 内容
        content = result.get("content_normalized", "")
        if content:
            self.log(f"\n📝 修正内容:", "info")
            self.log(f"   {content}", "info")
        
        # 结构化数据
        self.log(f"\n📊 结构化数据:", "info")
        
        user_id = result.get("user_id")
        if user_id:
            self.log(f"   👤 工号/呼号: {user_id}", "info")
        
        signal = result.get("signal_quality")
        if signal:
            self.log(f"   📶 信号质量: {signal}", "info")
        
        location = result.get("location")
        if location:
            self.log(f"   📍 位置: {location}", "info")
        
        action = result.get("action")
        if action:
            self.log(f"   🎯 动作/指令: {action}", "info")
        
        # 置信度
        confidence = result.get("confidence", 0)
        self.log(f"   🎚️ 置信度: {confidence:.1%}", "info")
        
        # 判断依据
        reason = result.get("reason", "")
        if reason:
            self.log(f"\n💡 判断依据:", "step")
            self.log(f"   {reason}", "step")
    
    def run_compare(self):
        """运行对比分析"""
        if not self.input_file:
            return
        
        self.btn_compare.config(state=tk.DISABLED)
        self.btn_run.config(state=tk.DISABLED)
        self.txt_log.delete(1.0, tk.END)
        
        # 启动对比处理线程
        threading.Thread(target=self._process_compare_pipeline, daemon=True).start()
    
    def _process_compare_pipeline(self):
        """对比处理流水线 - 分别处理原始音频和处理后音频"""
        temp_original = "temp_original_upload.wav"
        temp_processed = "temp_processed_upload.wav"
        
        try:
            # ===== Part 1: 处理原始音频 (不降噪) =====
            self.root.after(0, lambda: self.lbl_status.config(text="处理原始音频..."))
            self.log("=" * 60, "step")
            self.log("【对比分析】Part 1: 原始音频 (不降噪)", "info")
            self.log("=" * 60, "step")
            
            # 转换为API格式 (不降噪)
            self.log("➤ 转换原始音频为API格式...", "step")
            if not AudioProcessor.convert_to_mono(self.input_file, temp_original):
                self.log("❌ 原始音频转换失败", "error")
                return
            
            # SenseVoice
            self.log("➤ SenseVoice 语音识别...", "step")
            success, ref_orig = AIClient.call_asr(temp_original)
            if not success:
                self.log(f"❌ ASR失败: {ref_orig}", "error")
                return
            
            if not ref_orig or len(ref_orig.strip()) < 1:
                self.log("🛑 原始音频无有效语音", "warn")
                return
            
            self.log(f"   原始ASR: {ref_orig}", "step")
            
            # Qwen3 分析
            self.log("➤ Qwen3 专家分析...", "step")
            success, result_orig = AIClient.call_expert_analysis(temp_original, ref_orig)
            if not success:
                self.log(f"❌ 分析失败: {result_orig}", "error")
                return
            
            # 解析原始结果
            try:
                orig_data = json.loads(result_orig.replace("```json", "").replace("```", "").strip())
                self._display_result_simple(orig_data, "【原始音频】")
            except:
                self.log(f"原始解析失败: {result_orig}", "warn")
            
            # ===== Part 2: 处理后音频 (DSP降噪) =====
            self.log("\n" + "=" * 60, "step")
            self.log("【对比分析】Part 2: DSP处理后音频", "info")
            self.log("=" * 60, "step")
            
            # DSP降噪
            self.root.after(0, lambda: self.lbl_status.config(text="DSP降噪中..."))
            self.log("➤ DSP降噪处理...", "step")
            
            success, msg = AudioProcessor.process_audio(
                self.input_file,
                self.processed_file,
                algorithm=self.nr_algorithm.get(),
                agc_mode=self.agc_mode.get()
            )
            
            if not success:
                self.log(f"❌ DSP处理失败: {msg}", "error")
                return
            
            self.log("   ✓ DSP处理完成", "step")
            
            # 转换为API格式
            self.log("➤ 转换处理后音频为API格式...", "step")
            if not AudioProcessor.convert_to_mono(self.processed_file, temp_processed):
                self.log("❌ 处理后音频转换失败", "error")
                return
            
            # SenseVoice
            self.log("➤ SenseVoice 语音识别...", "step")
            success, ref_proc = AIClient.call_asr(temp_processed)
            if not success:
                self.log(f"❌ ASR失败: {ref_proc}", "error")
                return
            
            if not ref_proc or len(ref_proc.strip()) < 1:
                self.log("🛑 处理后音频无有效语音", "warn")
                return
            
            self.log(f"   处理后ASR: {ref_proc}", "step")
            
            # Qwen3 分析
            self.log("➤ Qwen3 专家分析...", "step")
            success, result_proc = AIClient.call_expert_analysis(temp_processed, ref_proc)
            if not success:
                self.log(f"❌ 分析失败: {result_proc}", "error")
                return
            
            # 解析处理后结果
            try:
                proc_data = json.loads(result_proc.replace("```json", "").replace("```", "").strip())
                self._display_result_simple(proc_data, "【DSP处理后】")
            except:
                self.log(f"处理后解析失败: {result_proc}", "warn")
            
            # ===== 对比总结 =====
            self.log("\n" + "=" * 60, "step")
            self.log("【对比总结】", "info")
            self.log("=" * 60, "step")
            
            # 对比ASR结果
            self.log(f"\n📝 ASR识别对比:", "info")
            self.log(f"   原始: {ref_orig[:50]}..." if len(ref_orig) > 50 else f"   原始: {ref_orig}", "step")
            self.log(f"   处理后: {ref_proc[:50]}..." if len(ref_proc) > 50 else f"   处理后: {ref_proc}", "step")
            
            # 对比置信度
            orig_conf = orig_data.get("confidence", 0)
            proc_conf = proc_data.get("confidence", 0)
            
            self.log(f"\n🎚️ 置信度对比:", "info")
            self.log(f"   原始: {orig_conf:.1%}", "step")
            self.log(f"   处理后: {proc_conf:.1%}", "step")
            
            if proc_conf > orig_conf:
                self.log(f"   → DSP处理后置信度提升 +{(proc_conf-orig_conf)*100:.1f}%", "success")
            elif proc_conf < orig_conf:
                self.log(f"   → DSP处理后置信度下降 {(proc_conf-orig_conf)*100:.1f}%", "warn")
            else:
                self.log(f"   → 置信度无变化", "step")
            
            # 对比信号类型
            orig_type = orig_data.get("signal_type", "UNKNOWN")
            proc_type = proc_data.get("signal_type", "UNKNOWN")
            
            self.log(f"\n📡 信号类型对比:", "info")
            self.log(f"   原始: {orig_type}", "step")
            self.log(f"   处理后: {proc_type}", "step")
            
            if orig_type != proc_type:
                self.log(f"   → 信号类型判定发生变化!", "warn")
            
            # 结论
            self.log(f"\n💡 结论:", "info")
            if proc_conf > orig_conf and len(ref_proc) >= len(ref_orig):
                self.log(f"   ✓ DSP处理有助于提升识别效果", "success")
            elif proc_conf < orig_conf:
                self.log(f"   ⚠️ 此音频可能不需要DSP处理，原始效果更好", "warn")
            else:
                self.log(f"   → 两种方式效果相近", "step")
            
            self.root.after(0, lambda: self.lbl_status.config(text="对比完成"))
            
        except Exception as e:
            self.log(f"❌ 对比分析错误: {str(e)}", "error")
            self.root.after(0, lambda: self.lbl_status.config(text="错误"))
        
        finally:
            # 清理临时文件
            for f in [temp_original, temp_processed]:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass
            
            # 尝试删除处理后的临时文件
            try:
                if os.path.exists(self.processed_file):
                    os.remove(self.processed_file)
            except:
                pass
            
            self.root.after(0, lambda: self.btn_compare.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_run.config(state=tk.NORMAL))
    
    def _display_result_simple(self, result, prefix=""):
        """简洁显示单次分析结果"""
        sig_type = result.get("signal_type", "UNKNOWN")
        
        if prefix:
            self.log(f"\n{prefix}", "info")
        
        if sig_type == "NOISE":
            self.log(f"  🚫 判定: 噪音/无效信号", "error")
        else:
            self.log(f"  ✅ 判定: {sig_type}", "success")
        
        content = result.get("content_normalized", "")
        if content:
            self.log(f"  📝 内容: {content[:60]}..." if len(content) > 60 else f"  📝 内容: {content}", "step")
        
        confidence = result.get("confidence", 0)
        self.log(f"  🎚️ 置信度: {confidence:.1%}", "step")
    
    def analyze_audio_quality(self, audio_path):
        """分析音频质量 - 轻量级检测"""
        try:
            import numpy as np
            
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
            for i in range(min(n_frames, 50)):  # 只分析前50帧
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
            
            return {
                "rms_db": rms_db,
                "peak_db": peak_db,
                "noise_db": noise_db,
                "snr_db": snr_db,
                "dynamic_range_db": dynamic_range,
                "sample_rate": params.framerate,
                "duration": len(audio) / params.framerate
            }
        except Exception as e:
            print(f"音频分析错误: {e}")
            return None
    
    def suggest_dsp_needed(self, quality):
        """根据音频质量建议是否需要DSP处理"""
        snr = quality.get("snr_db", 0)
        noise = quality.get("noise_db", -60)
        
        # 判断逻辑
        if snr > 20:
            # 信噪比很好，基本不需要降噪
            return {
                "needed": False,
                "reason": f"信噪比很高 ({snr:.1f}dB)，音频本身很清晰",
                "level": "LOW"
            }
        elif snr > 10:
            # 中等信噪比，可以尝试但不是必须的
            return {
                "needed": True,
                "reason": f"信噪比中等 ({snr:.1f}dB)，DSP可能有轻微改善",
                "level": "MEDIUM"
            }
        elif snr > 0:
            # 信噪比较低，需要降噪
            return {
                "needed": True,
                "reason": f"信噪比较低 ({snr:.1f}dB)，建议使用DSP降噪",
                "level": "HIGH"
            }
        else:
            # 信噪比很低
            return {
                "needed": True,
                "reason": f"信噪比很低 ({snr:.1f}dB)，强烈建议使用DSP降噪",
                "level": "VERY_HIGH"
            }
    
    def run_smart_analysis(self):
        """运行智能分析 - 自动判断是否需要DSP"""
        if not self.input_file:
            return
        
        self.btn_smart.config(state=tk.DISABLED)
        self.btn_run.config(state=tk.DISABLED)
        self.btn_compare.config(state=tk.DISABLED)
        self.txt_log.delete(1.0, tk.END)
        
        threading.Thread(target=self._process_smart_pipeline, daemon=True).start()
    
    def _process_smart_pipeline(self):
        """智能分析流水线"""
        temp_original = "temp_smart_original.wav"
        temp_processed = "temp_smart_processed.wav"
        
        try:
            # ===== Step 1: 音频质量分析 =====
            self.root.after(0, lambda: self.lbl_status.config(text="分析音频质量..."))
            self.log("=" * 60, "step")
            self.log("🧠 智能分析模式", "info")
            self.log("=" * 60, "step")
            
            self.log("➤ 步骤1: 分析原始音频质量...", "step")
            quality = self.analyze_audio_quality(self.input_file)
            
            if quality:
                self.log(f"   📊 音频质量指标:", "step")
                self.log(f"      RMS电平: {quality['rms_db']:.1f} dB", "step")
                self.log(f"      峰值电平: {quality['peak_db']:.1f} dB", "step")
                self.log(f"      噪声底噪: {quality['noise_db']:.1f} dB", "step")
                self.log(f"      信噪比: {quality['snr_db']:.1f} dB", "step")
                self.log(f"      动态范围: {quality['dynamic_range_db']:.1f} dB", "step")
                self.log(f"      时长: {quality['duration']:.1f} 秒", "step")
            
            # ===== Step 2: 判断是否需要DSP =====
            suggestion = self.suggest_dsp_needed(quality)
            
            self.log(f"\n➤ 步骤2: 智能判断...", "step")
            self.log(f"   💡 建议: {'需要DSP处理' if suggestion['needed'] else '不需要DSP处理'}", 
                     "success" if not suggestion['needed'] else "warn")
            self.log(f"   📝 理由: {suggestion['reason']}", "step")
            self.log(f"   🎯 处理级别: {suggestion['level']}", "step")
            
            # ===== Step 3: 实际处理对比 =====
            self.log(f"\n➤ 步骤3: 实际处理验证...", "step")
            
            # 转换原始音频
            self.log("   处理原始音频...", "step")
            if not AudioProcessor.convert_to_mono(self.input_file, temp_original):
                self.log("❌ 原始音频转换失败", "error")
                return
            
            # DSP处理
            self.log("   DSP降噪处理...", "step")
            success, msg = AudioProcessor.process_audio(
                self.input_file,
                temp_processed,
                algorithm=self.nr_algorithm.get(),
                agc_mode=self.agc_mode.get()
            )
            
            if not success:
                self.log(f"❌ DSP处理失败: {msg}", "error")
                return
            
            # 分析处理后质量
            proc_quality = self.analyze_audio_quality(temp_processed)
            if proc_quality:
                self.log(f"   处理后信噪比: {proc_quality['snr_db']:.1f} dB (原始: {quality['snr_db']:.1f} dB)", "step")
            
            # ===== Step 4: ASR对比 =====
            self.log(f"\n➤ 步骤4: ASR识别对比...", "step")
            
            # 原始ASR
            success, ref_orig = AIClient.call_asr(temp_original)
            if not success:
                self.log(f"❌ ASR失败", "error")
                return
            
            self.log(f"   原始ASR: {ref_orig[:40]}..." if len(ref_orig) > 40 else f"   原始ASR: {ref_orig}", "step")
            
            # 处理后ASR
            success, ref_proc = AIClient.call_asr(temp_processed)
            if not success:
                self.log(f"❌ ASR失败", "error")
                return
            
            self.log(f"   处理ASR: {ref_proc[:40]}..." if len(ref_proc) > 40 else f"   处理ASR: {ref_proc}", "step")
            
            # ===== Step 5: 专家分析对比 =====
            self.log(f"\n➤ 步骤5: 专家分析...", "step")
            
            # 原始分析
            success, res_orig = AIClient.call_expert_analysis(temp_original, ref_orig)
            orig_result = {}
            if success:
                try:
                    orig_result = json.loads(res_orig.replace("```json", "").replace("```", "").strip())
                except:
                    pass
            
            # 处理后分析
            success, res_proc = AIClient.call_expert_analysis(temp_processed, ref_proc)
            proc_result = {}
            if success:
                try:
                    proc_result = json.loads(res_proc.replace("```json", "").replace("```", "").strip())
                except:
                    pass
            
            # ===== Step 6: 智能选择 =====
            orig_conf = orig_result.get("confidence", 0)
            proc_conf = proc_result.get("confidence", 0)
            
            self.log(f"\n➤ 步骤6: 智能选择...", "step")
            self.log(f"   🎚️ 原始置信度: {orig_conf:.1%}", "step")
            self.log(f"   🎚️ 处理置信度: {proc_conf:.1%}", "step")
            
            # 最终选择
            if proc_conf > orig_conf:
                use_processed = True
                final_conf = proc_conf
                final_result = proc_result
                final_ref = ref_proc
                self.log(f"   ✅ 选择: DSP处理后的音频 (置信度提升 +{(proc_conf-orig_conf)*100:.1f}%)", "success")
            else:
                use_processed = False
                final_conf = orig_conf
                final_result = orig_result
                final_ref = ref_orig
                self.log(f"   ✅ 选择: 原始音频 (DSP处理反而降低置信度 {(orig_conf-proc_conf)*100:.1f}%)", "success")
            
            # ===== Step 7: 输出最终结果 =====
            self.log("\n" + "=" * 60, "step")
            self.log("📋 最终分析结果", "info")
            self.log("=" * 60, "step")
            
            sig_type = final_result.get("signal_type", "UNKNOWN")
            if sig_type == "NOISE":
                self.log(f"🚫 信号类型: 噪音/无效", "error")
            else:
                self.log(f"✅ 信号类型: {sig_type}", "success")
            
            content = final_result.get("content_normalized", "")
            if content:
                self.log(f"📝 内容: {content}", "info")
            
            user_id = final_result.get("user_id")
            if user_id:
                self.log(f"👤 工号: {user_id}", "info")
            
            signal = final_result.get("signal_quality")
            if signal:
                self.log(f"📶 信号: {signal}", "info")
            
            self.log(f"🎚️ 置信度: {final_conf:.1%}", "info")
            
            # 清理临时文件
            for f in [temp_original, temp_processed]:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass
            
            try:
                if os.path.exists(self.processed_file):
                    os.remove(self.processed_file)
            except:
                pass
            
            self.root.after(0, lambda: self.lbl_status.config(text="智能分析完成"))
            
        except Exception as e:
            self.log(f"❌ 智能分析错误: {str(e)}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
            self.root.after(0, lambda: self.lbl_status.config(text="错误"))
        
        finally:
            self.root.after(0, lambda: self.btn_smart.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_run.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_compare.config(state=tk.NORMAL))


# ================= 入口 =================
if __name__ == "__main__":
    # 检查API Key
    if API_KEY == "sk-xxxxxxxxxxxxxxxxxxxxxxxx":
        print("⚠️ 请先在代码中配置你的 SiliconFlow API Key!")
        print("   文件位置: dsp_ai_tool.py")
        print("   修改位置: API_KEY = 'your-api-key'")
    
    root = tk.Tk()
    app = DSPAITool(root)
    root.mainloop()
