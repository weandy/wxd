[根目录](../CLAUDE.md) > **src**

# src 模块说明

## 模块职责

智能识别与 DSP 主链路，负责录音识别、质量分析、DSP 决策、AI 解析与微信推送。

## 入口与启动

- `src/main.py`: 智能识别主入口（支持 --scan, --status, --test-audio）

## 对外接口

- `src/recognizer.py`: 录音完成回调与并发识别队列
- `src/smart_processor.py`: DSP + AI 识别与专家分析
- `src/wx_pusher.py`: go-wxpush 关键词推送

## 关键依赖与配置

- `.env` 环境变量由 `src/config.py` 读取
- 主要配置项：BSHT 账号、SILICONFLOW API、DSP 参数、数据库路径
- 识别提示词：`src/prompts.md`, `src/prompts.json`

## 数据模型

- `src/database.py`: `AudioRecord`, `Recording`

## 测试与质量

- 未见独立 tests 目录；识别流程依赖运行时日志与抽样验证

## 常见问题 (FAQ)

- 若识别失败，优先检查 `SILICONFLOW_API_KEY` 与网络连通性
- DSP 处理强度依赖 SNR 阈值与算法配置

## 相关文件清单

- `src/main.py`
- `src/recognizer.py`
- `src/smart_processor.py`
- `src/wx_pusher.py`
- `src/config.py`
- `src/database.py`
- `src/prompts.md`
- `src/prompts.json`

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-03-04 | 初始化模块文档 |
