[根目录](../../CLAUDE.md) > [src](../) > **bsht**

# src/bsht 模块说明

## 模块职责

BSHT 协议与数据模型实现，包含 RTP/Heartbeat/Binary 协议解析、音频类型、模型与工具函数。

## 入口与启动

- `src/bsht/protocol/rtp.py`: RTP 包封装与解析

## 对外接口

- `src/bsht/protocol/base.py`
- `src/bsht/protocol/binary.py`
- `src/bsht/protocol/heartbeat.py`

## 关键依赖与配置

- `src/bsht/config.py`
- `src/bsht/utils/logger.py`

## 数据模型

- `src/bsht/models/user.py`
- `src/bsht/models/channel.py`
- `src/bsht/models/audio.py`

## 测试与质量

- 未发现独立测试文件

## 常见问题 (FAQ)

- 协议字段来源于反编译资料与实测数据，修改需谨慎验证

## 相关文件清单

- `src/bsht/protocol/rtp.py`
- `src/bsht/protocol/base.py`
- `src/bsht/protocol/binary.py`
- `src/bsht/protocol/heartbeat.py`
- `src/bsht/models/user.py`
- `src/bsht/models/channel.py`
- `src/bsht/models/audio.py`

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-03-04 | 初始化模块文档 |
