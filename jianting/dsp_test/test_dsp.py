"""
DSP处理测试脚本

使用方法:
    python test_dsp.py input.wav [output.wav]

示例:
    # 处理文件
    python test_dsp.py inputs/noisy_audio.wav
    
    # 指定输出
    python test_dsp.py inputs/noisy_audio.wav outputs/result.wav
"""

import os
import sys
import wave
import numpy as np
import argparse
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from dsp_chain import AudioDSPChain
from metrics import AudioMetrics


def load_wav(file_path: str) -> tuple:
    """加载WAV文件"""
    print(f"[加载] {file_path}")
    
    with wave.open(file_path, 'rb') as wf:
        # 获取参数
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        sample_width = wf.getsampwidth()
        
        # 读取数据
        raw_data = wf.readframes(n_frames)
        
        # 转换为numpy数组
        if sample_width == 2:
            audio = np.frombuffer(raw_data, dtype=np.int16)
            audio = audio.astype(np.float32) / 32768.0
        elif sample_width == 4:
            audio = np.frombuffer(raw_data, dtype=np.float32)
        else:
            raise ValueError(f"不支持的采样宽度: {sample_width}")
        
        # 立体声 -> 单声道
        if n_channels == 2:
            audio = audio.reshape(-1, 2)
            audio = audio.mean(axis=1)
        
        print(f"  采样率: {sample_rate} Hz")
        print(f"  声道数: {n_channels}")
        print(f"  帧数: {n_frames}")
        print(f"  时长: {n_frames/sample_rate:.2f} 秒")
        
        return audio, sample_rate


def save_wav(file_path: str, audio: np.ndarray, sample_rate: int):
    """保存WAV文件"""
    print(f"[保存] {file_path}")
    
    # 确保范围正确
    audio = np.clip(audio, -1.0, 1.0)
    
    # 转换为int16
    audio_int16 = (audio * 32767).astype(np.int16)
    
    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(1)  # 单声道
        wf.setsampwidth(2)  # 16位
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    
    print(f"  保存完成: {len(audio)/sample_rate:.2f} 秒")


def process_file(
    input_path: str,
    output_path: str = None,
    algorithm: str = "spectral",
    verbose: bool = True
,
    agc_mode: str = "webrtc"
):
    """
    处理音频文件
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        algorithm: 降噪算法
        verbose: 是否打印详情
        agc_mode: AGC模式
    """
    # 检查输入文件
    if not os.path.exists(input_path):
        print(f"[错误] 输入文件不存在: {input_path}")
        return
    
    # 创建输出目录
    if output_path:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    # 加载音频
    audio, sample_rate = load_wav(input_path)
    
    # 如果输入不是48kHz，重采样
    if sample_rate != 48000:
        print(f"[重采样] {sample_rate} -> 48000 Hz")
        audio = resample_audio(audio, sample_rate, 48000)
        sample_rate = 48000
    
    # 创建DSP处理链
    print(f"\n[处理] 使用算法: {algorithm}")
    chain = AudioDSPChain(
        sample_rate=sample_rate,
        frame_size=960,
        vad_enabled=False,
        noise_reduction_algorithm=algorithm,
        agc_mode=agc_mode
    )
    
    # 处理
    print("\n[处理中] 音频处理...")
    processed_audio, metrics = chain.process_with_metrics(audio)
    print("[处理完成]")
    
    # 打印指标
    metrics_computer = AudioMetrics(sample_rate)
    metrics_computer.print_metrics(metrics)
    
    # 保存结果
    if output_path:
        save_wav(output_path, processed_audio, sample_rate)
    
    return processed_audio, metrics


def resample_audio(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """简单重采样"""
    if orig_rate == target_rate:
        return audio
    
    ratio = target_rate / orig_rate
    new_length = int(len(audio) * ratio)
    
    # 线性插值
    indices = np.linspace(0, len(audio) - 1, new_length)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(
        description="DSP音频处理测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_dsp.py inputs/noisy.wav
  python test_dsp.py inputs/noisy.wav outputs/clean.wav
  python test_dsp.py inputs/noisy.wav -a wiener
  python test_dsp.py inputs/noisy.wav -a rnnoise
        """
    )
    
    parser.add_argument(
        "input",
        help="输入WAV文件路径"
    )
    
    parser.add_argument(
        "output",
        nargs="?",
        help="输出WAV文件路径 (默认: outputs/输入文件名_processed.wav)"
    )
    
    parser.add_argument(
        "-a", "--algorithm",
        choices=["timedomain", "spectral", "wiener", "rnnoise", "noisereduce", "auto"],
        default="timedomain",
        help="降噪算法 (默认: timedomain)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )
    
    parser.add_argument(
        "--agc",
        choices=["none", "simple", "webrtc", "enhanced"],
        default="webrtc",
        help="AGC模式 (默认: webrtc)"
    )
    
    args = parser.parse_args()
    
    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        # 默认输出到outputs目录
        input_name = Path(args.input).stem
        output_path = f"outputs/{input_name}_processed.wav"
    
    # 打印标题
    print("=" * 60)
    print("DSP音频处理测试工具")
    print("=" * 60)
    print(f"输入:   {args.input}")
    print(f"输出:   {output_path}")
    print(f"算法:   {args.algorithm}")
    print("=" * 60)
    
    # 处理
    try:
        process_file(
            args.input,
            output_path,
            algorithm=args.algorithm,
            verbose=args.verbose,
            agc_mode=args.agc
        )
        print("\n✅ 处理完成!")
        print(f"   输出文件: {output_path}")
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()