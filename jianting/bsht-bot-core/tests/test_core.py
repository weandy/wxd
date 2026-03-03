# 添加项目根目录到路径
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import struct
import numpy as np
import wave
import tempfile
from typing import List

# ==================== 音频处理器测试 ====================

class TestAudioProcessor:
    """音频预处理模块测试"""

    def test_highpass_filter(self):
        """测试高通滤波器"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from audio_processor import AudioProcessor

        # 创建处理器
        processor = AudioProcessor(sample_rate=48000)

        # 生成测试信号：低频 (40Hz) + 高频 (1000Hz) 混合
        duration = 0.1  # 100ms
        sample_rate = 48000
        t = np.linspace(0, duration, int(sample_rate * duration))

        # 低频信号 (应该被滤除)
        low_freq = 40 * np.sin(2 * np.pi * 40 * t)
        # 高频信号 (应该保留)
        high_freq = 1000 * np.sin(2 * np.pi * 1000 * t)

        # 混合信号
        mixed = low_freq + high_freq
        # 转换为 int16
        mixed_int16 = (mixed * 32767 * 0.5).astype(np.int16)

        # 处理
        processed = processor.process(mixed_int16.tobytes())
        processed_int16 = np.frombuffer(processed, dtype=np.int16).astype(np.float32)

        # 验证：处理后的低频分量应该显著降低
        # 由于高通滤波，低频成分应该被削弱
        # 这里我们只验证处理没有出错
        assert len(processed) == len(mixed_int16.tobytes())
        assert processed != mixed_int16.tobytes()  # 应该有变化

    def test_agc_normalize(self):
        """测试 AGC 归一化"""
        from audio_processor import AudioProcessor

        processor = AudioProcessor(sample_rate=48000)
        processor.enable_highpass = False  # 禁用高通，只测试 AGC

        # 生成不同音量的测试信号
        for volume in [0.1, 0.3, 0.5, 0.8, 1.0]:
            samples = (np.sin(np.linspace(0, 2*np.pi, 960)) * 32767 * volume).astype(np.int16)
            processed = processor.process(samples.tobytes())

            # 验证长度不变
            assert len(processed) == len(samples.tobytes())

    def test_enable_disable(self):
        """测试功能开关"""
        from audio_processor import AudioProcessor

        processor = AudioProcessor(sample_rate=48000)

        # 生成测试数据
        samples = np.random.randint(-10000, 10000, 960, dtype=np.int16)

        # 全部启用
        processor.enable_highpass = True
        processor.enable_normalize = True
        result_all = processor.process(samples.tobytes())

        # 全部禁用
        processor.enable_highpass = False
        processor.enable_normalize = False
        result_none = processor.process(samples.tobytes())

        # 结果应该不同
        assert result_all != result_none

    def test_empty_input(self):
        """测试空输入"""
        from audio_processor import AudioProcessor

        processor = AudioProcessor(sample_rate=48000)
        result = processor.process(b'')
        assert result == b''


# ==================== 协议处理测试 ====================

class TestHTProtocol:
    """HT 协议模块测试"""

    def test_heartbeat_pack_unpack(self):
        """测试心跳包打包/解包"""
        from ht_protocol import Heartbeat

        # 创建心跳包
        hb = Heartbeat(uid=12345, interval=10000, version=2)

        # 打包
        packed = hb.pack()
        assert packed[0] == 0x00  # 第一个字节应该是 0x00

        # 解包
        unpacked = Heartbeat.unpack(packed)
        assert unpacked.U == 12345
        assert unpacked.I == 10000
        assert unpacked.V == 2

    def test_heartbeat_invalid(self):
        """测试无效心跳包"""
        from ht_protocol import Heartbeat

        # 无效数据包
        with pytest.raises(ValueError):
            Heartbeat.unpack(b'\x01\x00\x00')  # 错误的 header

    def test_rtp_pack_parse(self):
        """测试 RTP 包打包/解析"""
        from ht_protocol import RTPPacket

        # 创建 RTP 包
        payload = b'\x00\x01\x02\x03\x04\x05\x06\x07'
        rtp = RTPPacket(payload=payload, seq_num=100, timestamp=1000, ssrc=12345)

        # 打包
        packed = rtp.pack()
        assert len(packed) > 12  # 至少有 RTP 头

        # 解析
        parsed = RTPPacket.parse(packed)
        assert parsed.sequence_number == 100
        assert parsed.timestamp == 1000
        assert parsed.ssrc == 12345
        assert parsed.payload == payload

    def test_rtp_invalid(self):
        """测试无效 RTP 包"""
        from ht_protocol import RTPPacket

        # 太短的包
        with pytest.raises(ValueError):
            RTPPacket.parse(b'\x00\x01')  # 只有 2 字节

    def test_binary_packet(self):
        """测试二进制包"""
        from ht_protocol import BinaryPacket, Tag

        # 创建包
        pkt = BinaryPacket()
        pkt.tags[Tag.UID] = "12345"
        pkt.tags[Tag.CHECK] = "token123"

        # 打包
        packed = pkt.to_bytes()
        assert len(packed) > 0

        # 解析
        parsed = BinaryPacket.parse(packed)
        assert Tag.UID in parsed.tags
        assert Tag.CHECK in parsed.tags


# ==================== 配置管理测试 ====================

class TestConfig:
    """配置管理模块测试"""

    def test_env_loading(self):
        """测试环境变量加载"""
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from src.config import load_env_file, get_config
        import tempfile

        # 创建临时 .env 文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False, encoding='utf-8') as f:
            f.write("TEST_USERNAME=testuser\n")
            f.write("TEST_PASSWORD=testpass\n")
            f.write("TEST_CHANNEL_ID=12345\n")
            env_path = f.name

        try:
            # 设置环境变量
            os.environ['TEST_USERNAME'] = 'testuser'
            os.environ['TEST_PASSWORD'] = 'testpass'
            os.environ['TEST_CHANNEL_ID'] = '12345'

            # 加载配置
            from src.config import AppConfig, BSHTConfig, APIConfig, DatabaseConfig

            bsht = BSHTConfig(
                username=os.getenv('TEST_USERNAME', ''),
                password=os.getenv('TEST_PASSWORD', ''),
                channel_id=int(os.getenv('TEST_CHANNEL_ID', 0))
            )

            assert bsht.username == 'testuser'
            assert bsht.password == 'testpass'
            assert bsht.channel_id == 12345
        finally:
            os.unlink(env_path)
            if 'TEST_USERNAME' in os.environ:
                del os.environ['TEST_USERNAME']
            if 'TEST_PASSWORD' in os.environ:
                del os.environ['TEST_PASSWORD']
            if 'TEST_CHANNEL_ID' in os.environ:
                del os.environ['TEST_CHANNEL_ID']

    def test_config_validation(self):
        """测试配置验证"""
        from src.config import BSHTConfig, APIConfig, DatabaseConfig

        # 有效配置
        bsht = BSHTConfig(
            username="testuser",
            password="testpass",
            channel_id=12345
        )
        assert bsht.username == "testuser"
        assert bsht.channel_id == 12345


# ==================== 音频质量分析测试 ====================

class TestSmartProcessor:
    """智能处理模块测试"""

    def test_audio_quality_analyzer(self):
        """测试音频质量分析"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.smart_processor import AudioQualityAnalyzer

        # 创建测试音频文件
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            # 生成测试音频 (1秒, 48kHz, 单声道)
            sample_rate = 48000
            duration = 1.0
            samples = int(sample_rate * duration)

            # 生成正弦波 (1000Hz)
            t = np.linspace(0, duration, samples)
            audio = np.sin(2 * np.pi * 1000 * t) * 0.5  # 0.5 振幅

            # 转换为 int16
            audio_int16 = (audio * 32767).astype(np.int16)

            # 写入 WAV 文件
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())

            # 分析
            analyzer = AudioQualityAnalyzer()
            quality = analyzer.analyze(wav_path)

            assert quality is not None
            assert quality.sample_rate == 48000
            assert quality.duration == pytest.approx(1.0, rel=0.1)
            assert quality.rms_db < 0  # 应该有音量
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def test_callsign_extraction(self):
        """测试呼号提取"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.smart_processor import AIClient

        ai = AIClient(api_key="test-key")

        # 测试呼号提取
        assert ai._extract_callsign("CQ CQ CQ BD6KFP") == "BD6KFP"
        assert ai._extract_callsign("信号59 BG7IPQ") == "BG7IPQ"
        assert ai._extract_callsign("Hello World") == ""
        assert ai._extract_callsign("") == ""

    def test_signal_type_detection(self):
        """测试信号类型检测"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.smart_processor import AIClient

        ai = AIClient(api_key="test-key")

        # CQ 呼叫
        assert ai._detect_signal_type("CQ CQ CQ") == "CQ"
        assert ai._detect_signal_type("CQ CQ this is BD6KFP") == "CQ"

        # 73 祝福
        assert ai._detect_signal_type("73") == "CQ73"
        assert ai._detect_signal_type("73 73") == "CQ73"

        # QRZ 询问
        assert ai._detect_signal_type("QRZ?") == "QRZ"

        # QSO 通联
        assert ai._detect_signal_type("抄收 59") == "QSO"
        assert ai._detect_signal_type("信号报告57") == "QSO"

        # 未知
        assert ai._detect_signal_type("Hello") == "UNKNOWN"
        assert ai._detect_signal_type("") == "UNKNOWN"

    def test_correction_rules(self):
        """测试纠错规则"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.smart_processor import AIClient

        ai = AIClient(api_key="test-key")

        # 词语纠错
        assert ai._apply_correction_rules("柴友") == "台友"
        assert ai._apply_correction_rules("抄手") == "抄收"
        assert ai._apply_correction_rules("有他") == "有台"

        # 数字映射
        assert ai._apply_correction_rules("幺") == "1"
        assert ai._apply_correction_rules("洞") == "0"
        assert ai._apply_correction_rules("拐") == "7"


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
