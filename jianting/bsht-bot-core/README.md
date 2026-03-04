# BSHT Bot Core - 纯 Bot 核心模块

> 脱离 Web 前端的纯 Bot 服务，可独立运行

## 目录结构

```
bsht-bot-core/
├── bot_server.py       # Bot 主服务器入口
├── bsht_client.py      # gRPC 客户端
├── audio_codec.py      # Opus 音频编解码
├── audio_mixer.py      # 多用户音频混音
├── channel_recorder.py # 频道录音
├── jitter_buffer.py   # RTP 抖动缓冲
├── ht_protocol.py     # 协议处理
├── channel_worker.py  # 频道工作线程
├── run_bot.py         # 纯 Bot 启动脚本
├── src/
│   ├── database.py    # SQLite 数据库
│   ├── recognizer.py  # 伪实时识别器
│   ├── smart_processor.py  # AI 音频处理
│   ├── bot_state.py   # Bot 状态管理
│   ├── wx_pusher.py  # 微信推送
│   ├── config.py      # 配置管理
│   ├── logging_setup.py  # 日志配置
│   ├── main.py        # 智能机器人入口
│   └── bsht/          # BSHT 子模块
├── data/              # 数据库目录
├── recordings/        # 录音文件目录
├── logs/              # 日志目录
└── .env               # 配置文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `.env` 文件：

```env
BSHT_USERNAME=your_username
BSHT_PASSWORD=your_password
BSHT_CHANNEL_ID=your_channel_id
BSHT_CHANNEL_PASSCODE=0

# 可选：语音识别
SILICONFLOW_API_KEY=your_api_key

# 可选：微信推送
WXPUSH_URL=https://your-push-service.com
WXPUSH_TOKEN=your_token
WXPUSH_TARGETS=userid:名称:关键词
```

### 3. 启动

```bash
# 启动 Bot
python run_bot.py

# 禁用语音识别
python run_bot.py --no-asr

# 启用控制台 PTT
python run_bot.py --console-ptt
```

## 功能特性

| 功能 | 说明 |
|------|------|
| gRPC 通信 | 连接 BSHT 服务器 |
| 实时语音 | Opus 编解码 |
| 多用户混音 | 支持多人同时通话 |
| 频道录音 | 按用户/日期分类存储 |
| 语音识别 | 伪实时识别录音文件 |
| 微信推送 | 识别结果推送到微信 |
| 控制台 PTT | 键盘按键说话 |

## 命令行参数

```
--no-asr          禁用语音识别功能
--console-ptt     启用控制台 PTT 按键说话
--username        BSHT 用户名（覆盖 .env）
--password        BSHT 密码（覆盖 .env）
--channel-id      频道 ID（覆盖 .env）
--channel-passcode  频道密码（覆盖 .env）
```

## 与原项目区别

| 特性 | 原项目 (jianting) | 本项目 (bsht-bot-core) |
|------|------------------|----------------------|
| Web 前端 | ✅ | ❌ |
| SocketIO | ✅ | ❌ |
| 独立进程 | ❌ 多进程/合并 | ✅ 纯 Bot |
| 依赖项 | 较多 | 精简 |

## 后续升级方向

- [ ] 模块化重构
- [ ] 异步优化
- [ ] 配置热更新
- [ ] 插件系统
- [ ] 多频道支持增强
