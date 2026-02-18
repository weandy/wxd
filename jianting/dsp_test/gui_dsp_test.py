"""
GUI DSP Audio Processing Test Tool
GUI版本的DSP音频处理测试工具
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import threading
import numpy as np
import wave
import pyaudio
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dsp_chain import AudioDSPChain
from metrics import AudioMetrics


class AudioPlayer:
    """音频播放器 - 使用回调机制避免卡死"""
    
    def __init__(self):
        self.pyaudio = None
        self.stream = None
        self.is_playing = False
        self.play_thread = None
        self.wf = None
        self._lock = threading.Lock()
    
    def _init_pyaudio(self):
        if self.pyaudio is None:
            self.pyaudio = pyaudio.PyAudio()
    
    def play_wav(self, wav_path: str, callback=None):
        """播放WAV文件 - 非阻塞"""
        with self._lock:
            if self.is_playing:
                self._force_stop()
        
        # 在新线程中播放
        self.play_thread = threading.Thread(
            target=self._play_thread, 
            args=(wav_path, callback),
            daemon=True
        )
        self.play_thread.start()
    
    def _play_thread(self, wav_path: str, callback):
        """播放线程"""
        wf = None
        stream = None
        try:
            self._init_pyaudio()
            
            # 打开WAV文件
            wf = wave.open(wav_path, 'rb')
            self.wf = wf  # 保存引用
            
            # 创建播放流
            stream = self.pyaudio.open(
                format=self.pyaudio.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
                frames_per_buffer=1024
            )
            self.stream = stream  # 保存引用
            
            self.is_playing = True
            
            # 读取并播放数据
            chunk_size = 1024
            data = wf.readframes(chunk_size)
            
            while data and self.is_playing:
                stream.write(data)
                data = wf.readframes(chunk_size)
            
        except Exception as e:
            print(f"播放错误: {e}")
        finally:
            self._cleanup(wf, stream)
            # 调用callback
            if callback:
                try:
                    callback()
                except:
                    pass
    
    def _cleanup(self, wf=None, stream=None):
        """清理资源"""
        self.is_playing = False
        
        # 清理stream
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
            
        # 清理wf
        if wf:
            try:
                wf.close()
            except:
                pass
        if self.wf:
            try:
                self.wf.close()
            except:
                pass
            self.wf = None
    
    def _force_stop(self):
        """强制停止播放"""
        self.is_playing = False
        self._cleanup()
    
    def stop(self):
        """停止播放 - 在新线程中执行避免阻塞"""
        if not self.is_playing:
            return
        
        # 设置标志让播放线程自行停止
        self.is_playing = False
        
        # 等待一小段时间让播放线程结束
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=0.5)
        
        # 强制清理
        self._force_stop()
    
    def close(self):
        """关闭PyAudio"""
        self.stop()
        if self.pyaudio:
            try:
                self.pyaudio.terminate()
            except:
                pass
            self.pyaudio = None


class DSPGUITestTool:
    """DSP音频处理GUI测试工具"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("DSP Audio Processing Test Tool - 工业对讲机音频处理测试")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # 音频播放器
        self.player = AudioPlayer()
        
        # 文件路径
        self.input_file = None
        self.output_file = None
        
        # DSP处理链
        self.dsp_chain = None
        
        # 创建UI
        self.create_widgets()
        
        # 窗口关闭时清理资源
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_widgets(self):
        """创建UI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === 1. 文件选择区域 ===
        file_frame = ttk.LabelFrame(main_frame, text="1. 选择音频文件", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        
        # 输入文件
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="输入文件:").pack(side=tk.LEFT)
        self.input_path_var = tk.StringVar(value="未选择文件")
        ttk.Label(input_frame, textvariable=self.input_path_var, foreground="blue").pack(side=tk.LEFT, padx=10)
        ttk.Button(input_frame, text="浏览...", command=self.select_input_file).pack(side=tk.RIGHT)
        
        # === 2. 算法选择区域 ===
        algo_frame = ttk.LabelFrame(main_frame, text="2. 选择处理算法", padding="10")
        algo_frame.pack(fill=tk.X, pady=5)
        
        # 降噪算法
        ttk.Label(algo_frame, text="降噪算法:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.nr_algorithm = tk.StringVar(value="timedomain")
        nr_combo = ttk.Combobox(algo_frame, textvariable=self.nr_algorithm, 
                                 values=["timedomain", "spectral", "wiener", "rnnoise", "noisereduce"], 
                                 state="readonly", width=15)
        nr_combo.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # AGC模式
        ttk.Label(algo_frame, text="AGC模式:").grid(row=0, column=2, sticky=tk.W, pady=5, padx=10)
        self.agc_mode = tk.StringVar(value="webrtc")
        agc_combo = ttk.Combobox(algo_frame, textvariable=self.agc_mode,
                                  values=["none", "simple", "webrtc", "enhanced"],
                                  state="readonly", width=15)
        agc_combo.grid(row=0, column=3, sticky=tk.W)
        
        # VAD开关
        self.vad_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(algo_frame, text="启用VAD语音检测", variable=self.vad_enabled).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # === 3. 处理按钮区域 ===
        process_frame = ttk.Frame(main_frame)
        process_frame.pack(fill=tk.X, pady=10)
        
        self.process_btn = ttk.Button(process_frame, text="开始处理", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(process_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.LEFT, padx=10)
        
        # === 4. 播放对比区域 ===
        play_frame = ttk.LabelFrame(main_frame, text="3. 播放对比", padding="10")
        play_frame.pack(fill=tk.X, pady=5)
        
        # 播放按钮
        btn_frame = ttk.Frame(play_frame)
        btn_frame.pack(fill=tk.X)
        
        self.play_original_btn = ttk.Button(btn_frame, text="▶ 播放原始音频", 
                                             command=self.play_original, state=tk.DISABLED)
        self.play_original_btn.pack(side=tk.LEFT, padx=5)
        
        self.play_processed_btn = ttk.Button(btn_frame, text="▶ 播放处理后音频", 
                                               command=self.play_processed, state=tk.DISABLED)
        self.play_processed_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="■ 停止播放", command=self.stop_playback)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # === 5. 处理结果区域 ===
        result_frame = ttk.LabelFrame(main_frame, text="4. 处理结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 结果文本框
        self.result_text = tk.Text(result_frame, height=15, width=70, font=("Consolas", 10))
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text.config(yscrollcommand=scrollbar.set)
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=5)
    
    def select_input_file(self):
        """选择输入文件"""
        filename = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")]
        )
        
        if filename:
            self.input_file = filename
            self.input_path_var.set(os.path.basename(filename))
            
            # 自动设置输出文件路径
            basename = os.path.basename(filename)
            name, ext = os.path.splitext(basename)
            output_dir = os.path.dirname(filename)
            self.output_file = os.path.join(output_dir, f"{name}_processed.wav")
            
            # 启用播放原始音频按钮
            self.play_original_btn.config(state=tk.NORMAL)
            self.play_processed_btn.config(state=tk.DISABLED)
            
            # 清除之前的结果
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"已选择文件: {filename}\n")
            self.result_text.insert(tk.END, f"输出将保存为: {self.output_file}\n\n")
            self.result_text.insert(tk.END, "请选择算法后点击「开始处理」\n")
    
    def start_processing(self):
        """开始处理音频"""
        if not self.input_file:
            messagebox.showwarning("警告", "请先选择输入文件")
            return
        
        if not os.path.exists(self.input_file):
            messagebox.showerror("错误", "输入文件不存在")
            return
        
        # 禁用按钮
        self.process_btn.config(state=tk.DISABLED)
        self.progress.start(10)
        self.status_var.set("处理中...")
        
        # 在新线程中处理
        thread = threading.Thread(target=self.process_audio)
        thread.daemon = True
        thread.start()
    
    def process_audio(self):
        """处理音频（在线程中运行）"""
        try:
            # 读取音频文件
            with wave.open(self.input_file, 'rb') as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                n_frames = wf.getnframes()
                audio_data = wf.readframes(n_frames)
            
            # 转换为numpy数组
            audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if channels > 1:
                audio = audio[::channels]  # 转换为单声道
            
            # 创建DSP处理链
            self.dsp_chain = AudioDSPChain(
                sample_rate=sample_rate,
                frame_size=960,
                vad_enabled=self.vad_enabled.get(),
                noise_reduction_algorithm=self.nr_algorithm.get(),
                agc_mode=self.agc_mode.get()
            )
            
            # 处理音频
            processed = self.dsp_chain.process_audio(audio)
            
            # 计算指标
            metrics = AudioMetrics(sample_rate=sample_rate, frame_size=960)
            results = metrics.compute_full_metrics(audio, processed)
            
            # 保存处理后的音频
            self.save_wav(self.output_file, sample_rate, processed)
            
            # 更新UI
            self.root.after(0, self.update_result, results)
            
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
    
    def save_wav(self, filepath: str, sample_rate: int, audio: np.ndarray):
        """保存WAV文件"""
        # 转换回int16
        audio_int16 = (audio * 32768).astype(np.int16)
        
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())
    
    def update_result(self, results: dict):
        """更新结果显示"""
        self.progress.stop()
        self.process_btn.config(state=tk.NORMAL)
        self.status_var.set("处理完成")
        
        # 启用播放按钮
        self.play_processed_btn.config(state=tk.NORMAL)
        
        orig = results.get("original", {})
        proc = results.get("processed", {})
        
        # 计算变化值
        rms_change = proc.get('rms_db', 0) - orig.get('rms_db', 0)
        peak_change = proc.get('peak_db', 0) - orig.get('peak_db', 0)
        noise_change = orig.get('noise_floor_db', 0) - proc.get('noise_floor_db', 0)
        dynamic_change = proc.get('dynamic_range_db', 0) - orig.get('dynamic_range_db', 0)
        
        # SNR变化
        orig_snr = orig.get('snr_segment_db', 0)
        proc_snr = proc.get('snr_segment_db', 0)
        snr_change = proc_snr - orig_snr
        
        # 主观评分
        score = 50
        if snr_change > 5: score += 20
        elif snr_change > 0: score += 10
        if noise_change > 3: score += 15
        elif noise_change > 0: score += 8
        if rms_change > 3: score += 10
        elif rms_change > 0: score += 5
        if abs(dynamic_change) < 8: score += 5
        score = min(100, score)
        
        # 显示结果
        self.result_text.delete(1.0, tk.END)
        
        self.result_text.insert(tk.END, "=" * 60 + "\n")
        self.result_text.insert(tk.END, "        音频处理效果评估报告\n")
        self.result_text.insert(tk.END, "=" * 60 + "\n\n")
        
        # 表格格式
        self.result_text.insert(tk.END, "┌─────────────────────┬───────────┬───────────┬──────────┐\n")
        self.result_text.insert(tk.END, "│        指标          │   原始   │  处理后   │   变化   │\n")
        self.result_text.insert(tk.END, "├─────────────────────┼───────────┼───────────┼──────────┤\n")
        
        # RMS
        rms_sym = "↑" if rms_change > 0 else "↓" if rms_change < 0 else "→"
        self.result_text.insert(tk.END, f"│ RMS音量             │ {orig.get('rms_db', 0):>7.1f}dB │ {proc.get('rms_db', 0):>7.1f}dB │ {rms_sym}{abs(rms_change):>5.1f}dB │\n")
        
        # 噪声底噪
        noise_sym = "✓" if noise_change > 0 else "✗" if noise_change < 0 else "→"
        self.result_text.insert(tk.END, f"│ 噪声底噪(低=好)    │ {orig.get('noise_floor_db', 0):>7.1f}dB │ {proc.get('noise_floor_db', 0):>7.1f}dB │ {noise_sym}{noise_change:>5.1f}dB │\n")
        
        # 动态范围
        dyn_sym = "✓" if abs(dynamic_change) < 8 else "⚠"
        self.result_text.insert(tk.END, f"│ 动态范围           │ {orig.get('dynamic_range_db', 0):>7.1f}dB │ {proc.get('dynamic_range_db', 0):>7.1f}dB │ {dyn_sym}{dynamic_change:>5.1f}dB │\n")
        
        # SNR
        snr_sym = "✓" if snr_change > 0 else "✗" if snr_change < 0 else "→"
        self.result_text.insert(tk.END, f"│ SNR信噪比(高=好)   │ {orig_snr:>7.1f}dB │ {proc_snr:>7.1f}dB │ {snr_sym}{snr_change:>+5.1f}dB │\n")
        
        self.result_text.insert(tk.END, "└─────────────────────┴───────────┴───────────┴──────────┘\n\n")
        
        # 效果总结
        self.result_text.insert(tk.END, "【效果总结】\n")
        
        if noise_change > 2:
            self.result_text.insert(tk.END, "  ✓ 降噪效果明显\n")
        elif noise_change > 0:
            self.result_text.insert(tk.END, "  ○ 降噪有轻微效果\n")
        else:
            self.result_text.insert(tk.END, "  ✗ 降噪效果不明显\n")
        
        if rms_change > 5:
            self.result_text.insert(tk.END, "  ✓ 音量提升显著\n")
        elif rms_change > 0:
            self.result_text.insert(tk.END, "  ○ 音量有所提升\n")
        else:
            self.result_text.insert(tk.END, "  ✗ 音量变化不明显\n")
        
        if snr_change > 5:
            self.result_text.insert(tk.END, "  ✓ 信噪比显著改善\n")
        elif snr_change > 0:
            self.result_text.insert(tk.END, "  ○ 信噪比有所改善\n")
        else:
            self.result_text.insert(tk.END, "  ✗ 信噪比变化不明显\n")
        
        # 评分
        self.result_text.insert(tk.END, f"\n【主观评分】: {score}/100 分\n")
        if score >= 80:
            self.result_text.insert(tk.END, "  → 处理效果优秀，语音清晰度明显提升\n")
        elif score >= 60:
            self.result_text.insert(tk.END, "  → 处理效果良好，语音有一定改善\n")
        elif score >= 40:
            self.result_text.insert(tk.END, "  → 处理效果一般，建议调整参数\n")
        else:
            self.result_text.insert(tk.END, "  → 处理效果有限，可能需要更强算法\n")
        
        self.result_text.insert(tk.END, "\n" + "=" * 60 + "\n")
        self.result_text.insert(tk.END, f"输出文件: {self.output_file}\n")
        
        messagebox.showinfo("完成", "音频处理完成！点击「播放处理后音频」对比效果。")
    
    def show_error(self, error_msg: str):
        """显示错误"""
        self.progress.stop()
        self.process_btn.config(state=tk.NORMAL)
        self.status_var.set("处理失败")
        messagebox.showerror("错误", f"处理失败: {error_msg}")
    
    def play_original(self):
        """播放原始音频"""
        if self.input_file and os.path.exists(self.input_file):
            self.status_var.set("播放原始音频...")
            self.player.play_wav(self.input_file, self._on_play_finished)
            self.root.after(500, lambda: self.status_var.set("播放中..."))
    
    def play_processed(self):
        """播放处理后的音频"""
        if self.output_file and os.path.exists(self.output_file):
            self.status_var.set("播放处理后音频...")
            self.player.play_wav(self.output_file, self._on_play_finished)
            self.root.after(500, lambda: self.status_var.set("播放中..."))
    
    def _on_play_finished(self):
        """播放完成回调"""
        self.status_var.set("播放完成")
    
    def stop_playback(self):
        """停止播放 - 在后台线程执行"""
        # 先设置标志
        self.player.is_playing = False
        
        # 在新线程中等待并清理
        def do_stop():
            import time
            time.sleep(0.1)  # 给播放线程一点时间退出
            self.player._force_stop()
        
        stop_thread = threading.Thread(target=do_stop, daemon=True)
        stop_thread.start()
        
        self.status_var.set("已停止")
    
    def on_close(self):
        """关闭窗口"""
        self.player.close()
        self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()
    app = DSPGUITestTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()