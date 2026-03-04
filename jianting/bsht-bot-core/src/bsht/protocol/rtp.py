"""RTP packet handler"""
import struct
from typing import Optional


class RTPPacket:
    """RTP 包处理"""
    
    def __init__(self, payload: bytes = b'', seq_num: int = 0, timestamp: int = 0, ssrc: int = 0):
        self.version = 2
        self.padding = 0
        self.extension = 0
        self.csrc_count = 0
        self.marker = 0
        self.payload_type = 96
        self.sequence_number = seq_num
        self.timestamp = timestamp
        self.ssrc = ssrc
        self.payload = payload
        self.extension_data: Optional[bytes] = None

    def pack(self) -> bytes:
        """打包 RTP 包"""
        byte0 = (self.version << 6) | (self.padding << 5) | (self.extension << 4) | self.csrc_count
        byte1 = (self.marker << 7) | (self.payload_type & 0x7F)
        header = struct.pack('!BBHII', byte0, byte1, self.sequence_number, self.timestamp, self.ssrc)
        packet = header
        if self.extension and self.extension_data:
            ext_len = (len(self.extension_data) + 3) // 4
            ext_header = struct.pack('!HH', 0xBEDE, ext_len) 
            packet += ext_header + self.extension_data
            pad_len = (ext_len * 4) - len(self.extension_data)
            if pad_len > 0:
                packet += b'\x00' * pad_len
        packet += self.payload
        return packet

    @staticmethod
    def parse(data: bytes) -> 'RTPPacket':
        """解析 RTP 包"""
        if len(data) < 12:
            raise ValueError("Packet too short for RTP header")
        byte0, byte1, seq, ts, ssrc = struct.unpack('!BBHII', data[:12])
        pkt = RTPPacket()
        pkt.version = (byte0 >> 6) & 0x03
        pkt.padding = (byte0 >> 5) & 0x01
        pkt.extension = (byte0 >> 4) & 0x01
        pkt.csrc_count = byte0 & 0x0F
        pkt.marker = (byte1 >> 7) & 0x01
        pkt.payload_type = byte1 & 0x7F
        pkt.sequence_number = seq
        pkt.timestamp = ts
        pkt.ssrc = ssrc
        
        # Calculate header length
        header_len = 12 + (pkt.csrc_count * 4)
        
        # Handle extension
        if pkt.extension and len(data) > header_len + 4:
            ext_prof, ext_len = struct.unpack('!HH', data[header_len:header_len + 4])
            ext_start = header_len + 4
            pkt.extension_data = data[ext_start:ext_start + ext_len * 4]
            header_len = ext_start + ext_len * 4
        
        # Extract payload
        if len(data) > header_len:
            pkt.payload = data[header_len:]
        
        return pkt
