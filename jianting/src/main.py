"""
智能机器人服务器入口

使用环境变量配置:
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
    python src/main.py

或设置环境变量:
    $env:BSHT_USERNAME="username"
    $env:BSHT_PASSWORD="password"
    $env:BSHT_CHANNEL_ID="28951"
    $env:SILICONFLOW_API_KEY="your-api-key"
    python src/main.py
"""
import os
import sys
import logging
import argparse

# 添加src目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, AppConfig
from database import get_database, AudioRecord
from smart_processor import SmartAudioProcessor


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("smart_bot.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("SmartBot")


def process_audio_event(audio_path: str, channel_id: int, user_id: int, 
                        nickname: str, processor: SmartAudioProcessor, 
                        db, logger) -> None:
    """处理音频事件"""
    logger.info(f"处理音频: 用户={nickname}({user_id}), 频道={channel_id}")
    
    # 智能处理
    ai_result, quality, suggestion = processor.process(audio_path)
    
    # 记录到数据库
    record = AudioRecord(
        timestamp=ai_result.success and "" or None,
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
    logger.info(f"记录保存成功: ID={record_id}")
    
    # 输出结果
    if ai_result.success:
        logger.info(f"  信号类型: {ai_result.signal_type}")
        logger.info(f"  内容: {ai_result.content_normalized[:50]}...")
        logger.info(f"  置信度: {ai_result.confidence:.1%}")
    else:
        logger.error(f"  处理失败: {ai_result.error}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="智能机器人服务器")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--test-audio", "-t", help="测试音频文件路径")
    args = parser.parse_args()
    
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("智能机器人服务器启动")
    logger.info("=" * 60)
    
    # 加载配置
    config = get_config()
    valid, msg = config.validate()
    
    if not valid:
        logger.error(f"配置验证失败: {msg}")
        logger.info("请设置环境变量后重试")
        print("\n需要配置以下环境变量:")
        print("  BSHT_USERNAME - BSHT账号")
        print("  BSHT_PASSWORD - BSHT密码")
        print("  BSHT_CHANNEL_ID - 监听频道ID")
        print("  SILICONFLOW_API_KEY - SiliconFlow API密钥")
        return
    
    logger.info(f"BSHT账号: {config.bsht.username}")
    logger.info(f"监听频道: {config.bsht.channel_id}")
    logger.info(f"DSP启用: {config.dsp.enabled}")
    if config.dsp.enabled:
        logger.info(f"  算法: {config.dsp.algorithm}")
        logger.info(f"  AGC: {config.dsp.agc_mode}")
        logger.info(f"  SNR阈值: {config.dsp.snr_threshold_high}/{config.dsp.snr_threshold_low}")
    
    # 初始化数据库
    db = get_database(config.database.path)
    logger.info(f"数据库: {config.database.path}")
    
    # 测试音频模式
    if args.test_audio:
        logger.info(f"\n测试音频模式: {args.test_audio}")
        
        if not config.dsp.enabled:
            logger.warning("DSP未启用，使用原始音频")
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
        ai_result, quality, suggestion = processor.process(args.test_audio)
        
        print("\n" + "=" * 60)
        print("音频质量分析")
        print("=" * 60)
        print(f"  RMS电平: {quality.rms_db:.1f} dB")
        print(f"  峰值电平: {quality.peak_db:.1f} dB")
        print(f"  噪声底噪: {quality.noise_db:.1f} dB")
        print(f"  信噪比: {quality.snr_db:.1f} dB")
        print(f"  动态范围: {quality.dynamic_range_db:.1f} dB")
        print(f"  时长: {quality.duration:.1f} 秒")
        
        print("\nDSP建议")
        print("=" * 60)
        print(f"  需要处理: {'是' if suggestion.needed else '否'}")
        print(f"  原因: {suggestion.reason}")
        print(f"  级别: {suggestion.level}")
        
        if ai_result.success:
            print("\n识别结果")
            print("=" * 60)
            print(f"  信号类型: {ai_result.signal_type}")
            print(f"  内容: {ai_result.content}")
            print(f"  规范化内容: {ai_result.content_normalized}")
            print(f"  置信度: {ai_result.confidence:.1%}")
        else:
            print(f"\n识别失败: {ai_result.error}")
        
        # 保存到数据库
        record = AudioRecord(
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
            signal_type=ai_result.signal_type,
            content=ai_result.content,
            content_normalized=ai_result.content_normalized,
            confidence=ai_result.confidence,
            duration=quality.duration,
            audio_path=args.test_audio
        )
        
        record_id = db.add_record(record)
        print(f"\n记录已保存: ID={record_id}")
        
        return
    
    # 启动机器人服务
    logger.info("\n启动机器人服务...")
    logger.info("(完整机器人服务需要更多的集成代码)")
    logger.info("提示: 使用 --test-audio <file> 测试音频处理功能")


if __name__ == "__main__":
    main()
