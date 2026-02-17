"""Heartbeat protocol handler"""
import msgpack
from typing import Optional
from .base import ProtocolError


class Heartbeat:
    """心跳包"""
    
    def __init__(self, uid: int, interval: int = 10000, version: int = 2):
        self.U = uid      # 用户ID
        self.I = interval # 间隔(ms)
        self.V = version  # 版本

    def pack(self) -> bytes:
        """打包心跳包"""
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
        """解包心跳包"""
        if len(data) < 2 or data[0] != 0:
            raise ValueError("Invalid heartbeat packet")
        payload = msgpack.unpackb(data[1:], raw=False)
        return Heartbeat(
            uid=payload.get("U", 0),
            interval=payload.get("I", 10000),
            version=payload.get("V", 0)
        )
