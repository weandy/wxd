
import struct
import enum
import time
import msgpack
from typing import Dict, Any, Optional

class ProtocolError(Exception):
    pass

class AudioPacketType(enum.IntEnum):
    """音频包类型 (参考 EnumC6128n1.java)"""
    UNKNOWN = 0
    TX_AUDIO = 1        # 发射音频
    TX_AUDIO_STOP = 2   # 发射停止
    RX_AUDIO = 3        # 接收音频
    RX_AUDIO_STOP = 4   # 接收停止
    SET_SIGN_DATA = 5   # 设置签名数据


class Tag(enum.IntEnum):
    UID = 2
    CHECK = 39
    CHANNEL = 8
    # Add others as needed

class BinaryPacket:
    def __init__(self):
        self.tags: Dict[int, Any] = {}

    def to_bytes(self) -> bytes:
        data = b''
        for tag, value in self.tags.items():
            if isinstance(value, str):
                val_bytes = value.encode('utf-8')
            elif isinstance(value, bytes):
                val_bytes = value
            elif isinstance(value, int):
                val_bytes = str(value).encode('utf-8')
            else:
                val_bytes = str(value).encode('utf-8')
            
            data += struct.pack('!BH', tag, len(val_bytes)) + val_bytes
        return data

    @staticmethod
    def create_login_packet(user_id: int, token: str) -> 'BinaryPacket':
        pkt = BinaryPacket()
        pkt.tags[Tag.UID] = str(user_id)
        pkt.tags[Tag.CHECK] = token
        return pkt

    @staticmethod
    def parse(data: bytes) -> 'BinaryPacket':
        pkt = BinaryPacket()
        offset = 0
        while offset < len(data):
            if offset + 3 > len(data):
                break
            tag = data[offset]
            length = struct.unpack('!H', data[offset+1:offset+3])[0]
            offset += 3
            if offset + length > len(data):
                break
            value = data[offset:offset+length]
            pkt.tags[tag] = value
            offset += length
        return pkt

class AX25Packet:
    pass

class Heartbeat:
    def __init__(self, uid: int, interval: int = 10000, version: int = 2):
        self.U = uid
        self.I = interval
        self.V = version

    def pack(self) -> bytes:
        data = {}
        if self.U != 0:
            data["U"] = self.U
        if self.I != 0:
            data["I"] = self.I
        if self.V != 0:
            data["V"] = self.V
            
        packed = msgpack.packb(data, use_bin_type=True)
        return b'\x00' + packed

    @staticmethod
    def unpack(data: bytes) -> 'Heartbeat':
        if len(data) < 2 or data[0] != 0:
            raise ValueError("Invalid heartbeat packet")
        payload = msgpack.unpackb(data[1:], raw=False)
        return Heartbeat(
            uid=payload.get("U", 0),
            interval=payload.get("I", 10000),
            version=payload.get("V", 0)
        )

class RTPPacket:
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
        offset = 12 + (pkt.csrc_count * 4)
        if pkt.extension:
            if len(data) < offset + 4:
                 raise ValueError("Packet too short for Extension header")
            profile, length = struct.unpack('!HH', data[offset:offset+4])
            offset += 4
            ext_bytes = length * 4
            if len(data) < offset + ext_bytes:
                raise ValueError("Packet too short for Extension data")
            pkt.extension_data = data[offset:offset+ext_bytes]
            offset += ext_bytes
        pkt.payload = data[offset:]
        return pkt

class HTPacket:
    @staticmethod
    def parse(data: bytes):
        if len(data) == 0:
             return None
        # Heuristic detection
        if data[0] == 0x00:
            try:
                return Heartbeat.unpack(data)
            except:
                pass
        
        # RTP detection (Version 2 => 10xxxxxx => 0x80 bit set?)
        # RTP header byte 0: V=2 (10), P, X, CC. so 0x80 <= b0 <= 0xBF
        if (data[0] & 0xC0) == 0x80:
             try:
                 return RTPPacket.parse(data)
             except:
                 pass

        if len(data) > 0 and data[0] % 2 != 0:
            return BinaryPacket.parse(data)
            
        return AX25Packet()
