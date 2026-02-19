# 启动指南

## 三种启动模式

### 模式 1: 只运行 Bot
```bash
python bot_server.py
```

### 模式 2: 只运行 Web
```bash
python run_web.py
```

### 模式 3: 合并运行 (推荐)
```bash
python run_all.py
```

## 合并模式功能

- Bot 状态实时推送到 Web 界面
- 频道人数实时更新
- 新录音实时显示
- 用户说话状态实时显示
- 无需轮询数据库

## 调试日志

合并模式启动时会显示详细日志：
```
🚀 BSHT Bot 整合启动
🌐 启动 Web 服务...
🤖 启动 Bot 服务...
[WS] 连接到 ws://localhost:8080/bot...
[WS] ✅ 已连接到 Web 服务
[WS] 推送频道: 测试频道 (3人在线)
```

## 故障排查

1. **Web 服务无法启动**: 检查端口 8080 是否被占用
2. **Bot 无法连接 WS**: 检查 `BOT_WS_URL` 环境变量
3. **前端无实时更新**: 检查浏览器控制台 WebSocket 连接
