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
    
    # 2. 测试音频处理
    python src/main.py -t recordings/rx/xxx.wav
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
from database import get_database, AudioRecord
from smart_processor import SmartAudioProcessor, AudioQuality, DSPSuggestion, AIResult


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


def process_audio_event(audio_path: str, channel_id: int, user_id: int, 
                        nickname: str, processor: SmartAudioProcessor, 
                        db, logger, verbose: bool = True) -> AudioRecord:
    """处理音频事件"""
    if verbose:
        logger.info(f"收到音频: 用户={nickname}({user_id}), 频道={channel_id}")
        print(f"\n🔄 正在处理音频: {os.path.basename(audio_path)}")
    
    # 智能处理
    ai_result, quality, suggestion = processor.process(audio_path)
    
    # 打印结果到控制台
    if verbose:
        print_audio_result(ai_result, quality, suggestion)
    
    # 记录到数据库
    record = AudioRecord(
        timestamp=datetime.now().isoformat(),
        channel_id=channel_id,
        user_id=user_id,
        nickname=nickname,
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
        audio_path=audio_path
    )
    
    record_id = db.add_record(record)
    
    if verbose:
        logger.info(f"💾 记录已保存: ID={record_id}")
    
    return record


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="智能机器人服务器")
    parser.add_argument("--config", "-c", help="配置文件路径 (.env)")
    parser.add_argument("--test-audio", "-t", help="测试音频文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
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
    
    # 启动机器人服务
    print_banner("🚀 启动机器人服务")
    print("\n提示:")
    print("  - 使用 -t <file> 测试音频处理")
    print("  - 完整服务需要集成 bot_server.py")
    print("\n按 Ctrl+C 退出\n")


if __name__ == "__main__":
    main()