"""Binary packet handler"""
import struct
from typing import Dict, Any
from .base import Tag


class BinaryPacket:
    """二进制包处理"""
    
    def __init__(self):
        self.tags: Dict[int, Any] = {}

    def to_bytes(self) -> bytes:
        """打包为字节"""
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
        """创建登录包"""
        pkt = BinaryPacket()
        pkt.tags[Tag.UID] = str(user_id)
        pkt.tags[Tag.CHECK] = token
        return pkt

    @staticmethod
    def parse(data: bytes) -> 'BinaryPacket':
        """解析二进制包"""
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
    """AX.25 协议包（占位）"""
    pass
