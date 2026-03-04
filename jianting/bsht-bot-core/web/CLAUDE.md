[根目录](../CLAUDE.md) > **web**

# web 模块说明

## 模块职责

Web 控制台与权限模块，提供 Bot 管控、WebSocket 状态推送、PTT 传输与审计。

## 入口与启动

- `app.py`: Flask + SocketIO 入口
- `web/routes/websocket.py`: WebSocket 事件与 PTT 音频传输

## 对外接口

- `web/routes/bot.py`: Bot 状态、日志、重启
- `web/routes/websocket.py`: Bot WebSocket/客户端 WebSocket
- `ws_handler.py`: SocketIO 事件处理器

## 关键依赖与配置

- `web/models/database.py`: Web 管理数据库操作
- `config.py`: Web 控制台配置与账号

## 数据模型

- `web/models/database.py` (用户、审计、bot_status、bot_commands)
- `web/models/management_db.py`

## 测试与质量

- 未发现独立测试文件

## 常见问题 (FAQ)

- 若 Bot 状态为空，优先检查 `src.bot_state` 共享状态或数据库初始化

## 相关文件清单

- `app.py`
- `web/routes/bot.py`
- `web/routes/websocket.py`
- `ws_handler.py`
- `web/models/database.py`
- `web/models/management_db.py`

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-03-04 | 初始化模块文档 |
