"""
智能机器人服务器入口

使用 .env 文件配置:
- BSHT_USERNAME: BSHT账号
- BSHT_PASSWORD: BSHT密码
- BSHT_CHANNEL_ID: 监听频道ID
- BSHT_CHANNEL_PASSCODE: 频道密码(可选)

- SILICONFLOW_API_KEY: SiliconFlow API密钥
- SILICONFLOW_BASE_URL: API地址(可选)

- DSP_ENABLED: 是否启用DSP (true/false)
- DSP_ALGORITHM: 降噪算法 (timedomain/spectral/wiener/rnnoise)
- DSP_AGC_MODE: AGC模式 (simple/webrtc)
- DSP_SNR_THRESHOLD_HIGH: SNR高阈值(默认20)
- DSP_SNR_THRESHOLD_LOW: SNR低阈值(默认10)

- DATABASE_PATH: 数据库路径(默认data/records.db)
- DATABASE_MAX_RECORDS: 最大记录数(默认10000)

用法:
    # 1. 复制 .env.example 为 .env 并填写配置
    copy .env .env
    
    # 2. 启动服务 (伪实时识别)
    python src/main.py
    
    # 3. 扫描已有录音
    python src/main.py --scan
"""
import os
import sys
import logging
import argparse
import json
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, AppConfig, load_env_file
from database import get_database, AudioRecord, Recording
from smart_processor import SmartAudioProcessor, AudioQuality, DSPSuggestion, AIResult
from recognizer import RecordingRecognizer, create_recording_callback


def print_banner(text: str, width: int = 60):
    """打印带边框的横幅"""
    print("\n" + "=" * width)
    print(text.center(width))
    print("=" * width)


def print_audio_result(ai_result: AIResult, quality: AudioQuality, suggestion: DSPSuggestion):
    """打印音频识别结果到控制台"""
    print("\n" + "-" * 60)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    # 音频质量
    print("\n📊 音频质量分析:")
    print(f"   RMS电平:   {quality.rms_db:>7.1f} dB")
    print(f"   峰值电平: {quality.peak_db:>7.1f} dB")
    print(f"   噪声底噪: {quality.noise_db:>7.1f} dB")
    print(f"   信噪比:   {quality.snr_db:>7.1f} dB")
    print(f"   动态范围: {quality.dynamic_range_db:>7.1f} dB")
    print(f"   时长:     {quality.duration:>7.1f} 秒")
    
    # DSP建议
    print(f"\n🔊 DSP处理:")
    print(f"   需要处理: {'是 ✓' if suggestion.needed else '否 ✗'}")
    print(f"   原因:     {suggestion.reason}")
    print(f"   级别:     {suggestion.level}")
    
    # 识别结果
    if ai_result.success:
        print(f"\n📝 识别结果:")
        
        # 信号类型 (带颜色提示)
        signal_icons = {
            "CQ": "📡",
            "QSO": "📱", 
            "NOISE": "🔇",
            "UNKNOWN": "❓"
        }
        icon = signal_icons.get(ai_result.signal_type, "❓")
        print(f"   信号类型: {icon} {ai_result.signal_type}")
        
        if ai_result.content:
            print(f"   识别内容: {ai_result.content}")
        
        if ai_result.content_normalized:
            print(f"   规范化:   {ai_result.content_normalized}")
        
        if ai_result.user_id:
            print(f"   用户ID:   {ai_result.user_id}")
        
        if ai_result.signal_quality:
            # 信号质量可视化
            try:
                sq = int(ai_result.signal_quality)
                bars = "▮" * sq + "▯" * (9 - sq)
                print(f"   信号质量: [{bars}] {ai_result.signal_quality}/9")
            except:
                print(f"   信号质量: {ai_result.signal_quality}")
        
        # 置信度 (带进度条)
        conf = ai_result.confidence
        conf_bars = "█" * int(conf * 20) + "░" * (20 - int(conf * 20))
        conf_color = "🟢" if conf > 0.8 else "🟡" if conf > 0.5 else "🔴"
        print(f"   置信度:   {conf_color} [{conf_bars}] {conf*100:.1f}%")
    else:
        print(f"\n❌ 识别失败: {ai_result.error}")
    
    print("-" * 60)


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("smart_bot.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("SmartBot")


def show_recordings_status(db, limit: int = 20):
    """显示录音记录状态"""
    print("\n" + "=" * 60)
    print("📁 录音记录状态")
    print("=" * 60)
    
    # 统计
    all_recs = db.get_recordings(limit=10000)
    total = len(all_recs)
    recognized = sum(1 for r in all_recs if r.recognized)
    unrecognized = total - recognized
    
    print(f"\n总计: {total} 条录音")
    print(f"  ✅ 已识别: {recognized}")
    print(f"  ⏳ 未识别: {unrecognized}")
    
    # 显示最近录音
    recs = db.get_recordings(limit=limit)
    if recs:
        print(f"\n最近 {min(limit, len(recs))} 条录音:")
        print("-" * 60)
        for r in recs:
            status = "✅" if r.recognized else "⏳"
            type_icon = {"CQ": "📡", "QSO": "📱", "NOISE": "🔇", "UNKNOWN": "❓"}.get(r.signal_type, "❓")
            
            # 解析时间
            try:
                ts = datetime.fromisoformat(r.timestamp)
                time_str = ts.strftime("%H:%M:%S")
            except:
                time_str = r.timestamp[-8:] if len(r.timestamp) > 8 else r.timestamp
            
            print(f"  {status} [{r.recorder_type}] {time_str} | {r.user_name}")
            print(f"      文件: {r.filename}")
            if r.recognized:
                print(f"      {type_icon} {r.signal_type}: {r.asr_text[:30]}...")
                print(f"      置信度: {r.confidence*100:.1f}%")
            print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="智能机器人服务器")
    parser.add_argument("--config", "-c", help="配置文件路径 (.env)")
    parser.add_argument("--test-audio", "-t", help="测试音频文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--scan", "-s", action="store_true", help="扫描已有录音并识别")
    parser.add_argument("--status", action="store_true", help="查看录音记录状态")
    args = parser.parse_args()
    
    logger = setup_logging()
    
    print_banner("🤖 智能机器人服务器")
    
    # 加载配置
    env_path = args.config or ".env"
    load_env_file(env_path)
    config = get_config(env_path)
    
    valid, msg = config.validate()
    
    if not valid:
        print(f"\n❌ 配置验证失败: {msg}")
        print("\n请创建 .env 文件并配置以下内容:")
        print("-" * 40)
        
        # 读取.env模板
        env_example = ".env"
        if os.path.exists(env_example):
            with open(env_example, 'r', encoding='utf-8') as f:
                print(f.read())
        return
    
    # 显示配置信息
    print(f"\n✅ 配置加载成功")
    print(f"   账号: {config.bsht.username}")
    print(f"   频道: {config.bsht.channel_id}")
    print(f"   DSP:  {'启用' if config.dsp.enabled else '禁用'}")
    if config.dsp.enabled:
        print(f"         算法: {config.dsp.algorithm}")
        print(f"         SNR阈值: {config.dsp.snr_threshold_high}/{config.dsp.snr_threshold_low} dB")
    print(f"   数据库: {config.database.path}")
    
    # 初始化数据库
    db = get_database(config.database.path)
    
    # 查看状态模式
    if args.status:
        show_recordings_status(db)
        return
    
    # 测试音频模式
    if args.test_audio:
        audio_file = args.test_audio
        if not os.path.exists(audio_file):
            print(f"\n❌ 文件不存在: {audio_file}")
            return
        
        print_banner(f"🎵 测试音频处理")
        print(f"\n📁 文件: {audio_file}")
        
        if not config.dsp.enabled:
            print("\n⚠️  DSP未启用，跳过处理")
            return
        
        # 初始化智能处理器
        processor = SmartAudioProcessor(
            api_key=config.api.siliconflow_key,
            dsp_config={
                "algorithm": config.dsp.algorithm,
                "agc_mode": config.dsp.agc_mode,
                "snr_threshold_high": config.dsp.snr_threshold_high,
                "snr_threshold_low": config.dsp.snr_threshold_low
            }
        )
        
        # 处理测试音频
        ai_result, quality, suggestion = processor.process(audio_file)
        
        # 打印结果
        print_audio_result(ai_result, quality, suggestion)
        
        # 保存到数据库
        record = AudioRecord(
            timestamp=datetime.now().isoformat(),
            channel_id=0,
            user_id=0,
            nickname="test",
            rms_db=quality.rms_db,
            peak_db=quality.peak_db,
            noise_db=quality.noise_db,
            snr_db=quality.snr_db,
            dsp_needed=suggestion.needed,
            dsp_algorithm=suggestion.algorithm,
            dsp_applied=suggestion.needed,
            processed_snr_db=quality.snr_db + 10 if suggestion.needed else quality.snr_db,
            signal_type=ai_result.signal_type,
            content=ai_result.content,
            content_normalized=ai_result.content_normalized,
            confidence=ai_result.confidence,
            duration=quality.duration,
            audio_path=audio_file
        )
        
        record_id = db.add_record(record)
        print(f"\n💾 记录已保存: ID={record_id}")
        
        return
    
    # 扫描已有录音模式
    if args.scan:
        print_banner("🔍 扫描已有录音")
        
        if not config.dsp.enabled:
            print("\n⚠️  DSP未启用，无法识别")
            return
        
        # 创建识别器
        recognizer = RecordingRecognizer(
            api_key=config.api.siliconflow_key,
            dsp_config={
                "algorithm": config.dsp.algorithm,
                "agc_mode": config.dsp.agc_mode,
                "snr_threshold_high": config.dsp.snr_threshold_high,
                "snr_threshold_low": config.dsp.snr_threshold_low
            }
        )
        recognizer.set_database(db)
        
        # 先显示当前状态
        show_recordings_status(db)
        
        # 扫描处理
        print("\n开始扫描处理...")
        recognizer.process_existing_recordings("recordings", max_count=50)
        
        return
    
    # 启动机器人服务 (伪实时识别)
    print_banner("🚀 启动机器人服务 (伪实时识别)")
    
    if not config.dsp.enabled:
        print("\n⚠️  DSP未启用，只录制不识别")
        print("\n启动服务...")
        print("提示: 启动后请使用 Ctrl+C 退出\n")
        return
    
    # 创建识别器
    recognizer = RecordingRecognizer(
        api_key=config.api.siliconflow_key,
        dsp_config={
            "algorithm": config.dsp.algorithm,
            "agc_mode": config.dsp.agc_mode,
            "snr_threshold_high": config.dsp.snr_threshold_high,
            "snr_threshold_low": config.dsp.snr_threshold_low
        }
    )
    recognizer.set_database(db)
    
    # 创建回调
    recording_callback = create_recording_callback(recognizer)
    
    print("\n🎯 功能说明:")
    print("   - 录音完成后自动识别")
    print("   - 识别结果输出到控制台")
    print("   - 记录保存到数据库")
    print("\n📁 录音目录: recordings/日期/")
    print("   文件格式: 序号_用户ID_时间.wav")
    print("\n💡 常用命令:")
    print("   --status  查看录音记录状态")
    print("   --scan    扫描并识别已有录音")
    print("\n启动服务... (按 Ctrl+C 退出)\n")
    
    # TODO: 这里需要集成 bot_server.py 来启动实际服务
    # 暂时只显示提示信息
    print("⚠️  完整服务需要集成 bot_server.py")
    print("   当前仅提供识别器模块，可被 bot_server 调用")


if __name__ == "__main__":
    main()