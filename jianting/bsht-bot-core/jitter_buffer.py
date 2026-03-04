"""
抖动缓冲模块 (Jitter Buffer)

按序列号重排RTP包，处理乱序和丢包，为解码器提供平滑的帧流。

参考: HT应用典型通话流程详细分析.md §8.4
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger("JitterBuffer")


@dataclass
class BufferedFrame:
    """缓冲帧"""
    sequence: int
    opus_data: bytes
    ssrc: int = 0          # 发送者
    marker: bool = False   # RTP Marker位
    timestamp: float = 0   # 接收时间


class JitterBuffer:
    """
    抖动缓冲器
    
    功能:
    - 按序列号重新排序接收到的RTP帧
    - 检测丢包并标记 (返回 None 让 PLC 处理)
    - 检测说话者切换 (SSRC 变化)
    - 可配置缓冲深度
    
    用法:
        jb = JitterBuffer(target_depth=3)
        
        # 接收线程:
        jb.push(seq=1, opus_data=b'...', ssrc=12345)
        jb.push(seq=3, opus_data=b'...', ssrc=12345)  # seq=2 丢失
        
        # 播放线程:
        frame = jb.pop()  # → seq=1 的数据
        frame = jb.pop()  # → None (seq=2 丢包, 用PLC)
        frame = jb.pop()  # → seq=3 的数据
    """
    
    def __init__(self, target_depth: int = 3, max_depth: int = 50):
        """
        Args:
            target_depth: 目标缓冲深度 (帧数)，越大延迟越高但越平滑
            max_depth: 最大缓冲深度，超过则丢弃旧帧
        """
        self.target_depth = target_depth
        self.max_depth = max_depth

        self._buffer: dict[int, BufferedFrame] = {}  # {seq: frame}
        self._lock = threading.Lock()

        # 序列号追踪
        self._next_seq: Optional[int] = None   # 下一个期望的序列号
        self._initialized = False               # 是否已初始化 (收到第一个包)
        self._current_ssrc: int = 0             # 当前说话者

        # ========== 回绕检测增强 ==========
        self._last_seen_seq: Optional[int] = None  # 最后收到的序列号
        self._wrap_detected = False                # 是否检测到回绕
        self._wrap_count = 0                       # 回绕次数统计
        self._packets_since_wrap = 0               # 自上次回绕以来的包数

        # 统计
        self.total_pushed = 0
        self.total_popped = 0
        self.total_lost = 0        # 丢包数
        self.total_late = 0        # 迟到丢弃数
        self.total_reordered = 0   # 乱序修正数
    
    def push(self, sequence: int, opus_data: bytes,
             ssrc: int = 0, marker: bool = False):
        """
        将收到的RTP帧放入缓冲

        Args:
            sequence: RTP 序列号
            opus_data: Opus 编码数据
            ssrc: 发送者 SSRC
            marker: RTP Marker 位
        """
        with self._lock:
            # ========== 回绕检测增强 ==========
            if self._last_seen_seq is not None:
                gap = (sequence - self._last_seen_seq) & 0xFFFF

                # 检测大幅回退 (负方向差距大) = 可能的序列号回绕
                if gap > 0x8000 and not self._wrap_detected:
                    # 确认是真的回绕而不是乱序：检查是否已有后续序列号的包
                    is_wrap = True

                    # 如果缓冲区中有比当前序列号大的包，说明可能是乱序而非回绕
                    for buffered_seq in self._buffer.keys():
                        seq_diff = (buffered_seq - self._last_seen_seq) & 0xFFFF
                        if 0 < seq_diff < 0x8000:
                            # 有合理的后续包，可能不是回绕
                            is_wrap = False
                            break

                    if is_wrap:
                        self._wrap_detected = True
                        self._wrap_count += 1
                        self._packets_since_wrap = 0

                        logger.info(
                            f"[JB] 检测到序列号回绕 #{self._wrap_count}: "
                            f"{self._last_seen_seq} → {sequence} "
                            f"(回退 {0x10000 - gap})"
                        )

                        # 重置序列号追踪
                        self._next_seq = sequence
                        self._initialized = True

                        # 清理缓冲区中的旧包（回绕前的）
                        old_seqs = [
                            seq for seq in self._buffer.keys()
                            if (seq - sequence) & 0xFFFF > 0x8000
                        ]
                        for old_seq in old_seqs:
                            del self._buffer[old_seq]

                        if old_seqs:
                            logger.debug(f"[JB] 清理回绕前旧包: {len(old_seqs)} 个")

            # 更新最后看到的序列号
            self._last_seen_seq = sequence

            # 回绕后跟踪包数，用于后续判断是否恢复正常
            if self._wrap_detected:
                self._packets_since_wrap += 1
                # 收到100个包后，认为回绕已处理完毕
                if self._packets_since_wrap > 100:
                    self._wrap_detected = False

            # 说话者切换: 更新SSRC (不再清空buffer，避免丢帧)
            if ssrc != 0 and ssrc != self._current_ssrc:
                self._current_ssrc = ssrc
                # 新说话者: 重置序列号为当前帧
                self._next_seq = sequence
                self._initialized = True
                logger.debug(f"[JB] 说话者切换: ssrc={ssrc}, seq={sequence}")

            # Marker 位: 新talkspurt，重置序列号追踪 (不清空buffer)
            if marker and self._initialized:
                self._next_seq = sequence

            # 初始化: 第一个包决定起始序列号
            if not self._initialized:
                self._next_seq = sequence
                self._initialized = True
                logger.debug(f"[JB] 新session首帧: seq={sequence}, ssrc={ssrc}, marker={marker}")

            # 丢弃太旧的帧 (已经播放过的)
            if self._next_seq is not None:
                # 处理序列号回绕 (16位)
                diff = (sequence - self._next_seq) & 0xFFFF
                if diff > 0x8000:  # 负方向 = 太旧
                    self.total_late += 1
                    return

            # 存入缓冲
            self._buffer[sequence] = BufferedFrame(
                sequence=sequence,
                opus_data=opus_data,
                ssrc=ssrc,
                marker=marker,
                timestamp=time.time()
            )
            self.total_pushed += 1

            # 溢出保护: 丢弃最旧的帧
            while len(self._buffer) > self.max_depth:
                oldest_seq = min(self._buffer.keys())
                del self._buffer[oldest_seq]

            # 如果溢出导致 _next_seq 指向已被淘汰的帧，快进到缓冲区最小值
            # 这是丢包的核心修复: 避免 pop() 把被溢出删除的帧计为丢包
            if self._next_seq is not None and self._buffer:
                min_buffered = min(self._buffer.keys())
                diff = (min_buffered - self._next_seq) & 0xFFFF
                if 0 < diff < 0x8000:  # _next_seq 落后于缓冲最小值
                    self._next_seq = min_buffered
    
    def pop(self) -> Optional[BufferedFrame]:
        """
        取出下一帧 (按序列号)
        
        Returns:
            BufferedFrame: 正常帧
            None 但 total_lost 增加: 丢包 (调用方应使用 PLC)
        """
        with self._lock:
            if self._next_seq is None:
                return None
            
            seq = self._next_seq
            
            if seq in self._buffer:
                frame = self._buffer.pop(seq)
                self._next_seq = (seq + 1) & 0xFFFF
                self.total_popped += 1
                return frame
            else:
                # 帧不在缓冲中
                # 检查是否有更新的帧 (说明这个帧丢了)
                if self._buffer:
                    min_seq = min(self._buffer.keys())
                    diff = (min_seq - seq) & 0xFFFF
                    if diff < 0x8000 and diff > 0:
                        # 确实丢了，跳过这个序列号
                        self._next_seq = (seq + 1) & 0xFFFF
                        self.total_lost += 1
                        if self.total_lost <= 5 or self.total_lost % 10 == 0:
                            logger.info(f"[JB] 丢包#{self.total_lost}: 期望seq={seq}, 缓冲最小={min_seq}, 跳过{diff}帧, 缓冲深度={len(self._buffer)}")
                        return None  # 信号: 丢包，请 PLC
                
                # 缓冲中没有更新的帧，等待
                return None  # 信号: 缓冲空
    
    @property
    def depth(self) -> int:
        """当前缓冲深度"""
        with self._lock:
            return len(self._buffer)
    
    @property
    def is_ready(self) -> bool:
        """缓冲是否达到目标深度 (可以开始播放)"""
        return self.depth >= self.target_depth
    
    @property
    def loss_rate(self) -> float:
        """丢包率"""
        total = self.total_popped + self.total_lost
        if total == 0:
            return 0.0
        return self.total_lost / total
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "depth": self.depth,
            "pushed": self.total_pushed,
            "popped": self.total_popped,
            "lost": self.total_lost,
            "late": self.total_late,
            "loss_rate": f"{self.loss_rate:.1%}",
        }

    def reset(self):
        """重置缓冲"""
        with self._lock:
            self._buffer.clear()
            self._next_seq = None
            self._initialized = False
            self._current_ssrc = 0
            # 重置统计 (防止新session误计旧session的丢包)
            self.total_pushed = 0
            self.total_popped = 0
            self.total_lost = 0
            self.total_late = 0
            self.total_reordered = 0
