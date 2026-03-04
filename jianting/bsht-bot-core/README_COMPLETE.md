# BSHT Bot Web 管理平台

> 基于 Python + FastAPI + SQLite + Tailwind CSS 的微信助手 Bot 管理平台

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)]
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)]
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)]

## 📋 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [API 文档](#api-文档)
- [部署指南](#部署指南)
- [开发指南](#开发指南)
- [常见问题](#常见问题)

---

## 功能特性

### ✅ 已实现功能 (Phase 1-7)

#### Phase 1: 基础设施与认证
- 用户登录/登出
- Session 管理
- 权限控制
- 密码加密存储

#### Phase 2: 录音管理
- 录音列表查看（分页、筛选）
- 录音详情查看
- 录音播放
- 录音删除
- 批量操作
- 录音统计

#### Phase 3: 统计仪表板
- 实时统计卡片
- 录音趋势图表
- 识别率统计
- 用户活跃度分析
- 频道统计

#### Phase 4: 纠错规则管理
- 规则列表（CRUD）
- 规则启用/禁用
- 规则分类管理
- 规则匹配测试
- 批量导入/导出

#### Phase 5: 推送服务管理
- 推送服务配置
- 目标用户管理
- 推送历史记录
- 推送统计
- 关键词触发配置

#### Phase 6: 广播任务与音频库
- 广播任务管理
- 任务执行控制
- 音频库管理
- 音频上传/录制
- TTS 文本转语音

#### Phase 7: 机器人监控
- 系统资源监控（CPU、内存、磁盘）
- 实时日志查看
- 性能指标图表
- 频道状态监控
- 机器人控制（启动/停止/重启）

---

## 技术栈

### 后端
- **框架**: FastAPI 0.104+
- **数据库**: SQLite 3
- **认证**: Session + BCrypt 密码哈希
- **API 文档**: Swagger/OpenAPI

### 前端
- **框架**: Tailwind CSS 3.x
- **模板引擎**: Jinja2
- **图表**: Chart.js
- **样式**: 响应式设计

### 依赖工具
- **Python**: 3.8+
- **包管理**: pip
- **进程管理**: uvicorn
- **数据库 ORM**: 自定义 SQLite 封装

---

## 快速开始

### 环境要求

- Python 3.8 或更高版本
- pip 包管理器
- 至少 500MB 可用磁盘空间

### 安装步骤

1. **克隆仓库**
```bash
git clone <repository-url>
cd bsht-bot-core
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
copy .env.example .env
# 编辑 .env 文件，填写必要的配置
```

4. **初始化数据库**
```bash
python -c "from src.database import Database; Database().init_db()"
```

5. **启动 Web 服务器**
```bash
python web_server.py
```

6. **访问系统**
```
打开浏览器访问: http://localhost:8000
默认用户名: admin
默认密码: admin123
```

---

## API 文档

### 认证 API

#### POST /api/auth/login
用户登录

**请求体**:
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "username": "admin",
    "nickname": "管理员",
    "role": "admin"
  }
}
```

#### POST /api/auth/logout
用户登出

**响应**:
```json
{
  "code": 0,
  "message": "success"
}
```

#### GET /api/auth/me
获取当前用户信息

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "username": "admin",
    "nickname": "管理员",
    "role": "admin"
  }
}
```

### 录音管理 API

#### GET /api/recordings
获取录音列表

**查询参数**:
- `page`: 页码（默认: 1）
- `page_size`: 每页数量（默认: 20）
- `channel_id`: 频道ID筛选
- `user_id`: 用户ID筛选
- `recognized`: 识别状态筛选 (0/1)
- `start_date`: 开始日期
- `end_date`: 结束日期

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 317,
    "page": 1,
    "page_size": 20
  }
}
```

#### GET /api/recordings/{recording_id}
获取录音详情

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "filepath": "/path/to/recording.opus",
    "filename": "recording_001.opus",
    "channel_id": "123456",
    "user_id": "789",
    "duration": 120.5,
    "recognized": true,
    "asr_text": "识别的文本内容"
  }
}
```

#### DELETE /api/recordings/{recording_id}
删除录音

**响应**:
```json
{
  "code": 0,
  "message": "删除成功",
  "data": {"id": 1}
}
```

### 统计仪表板 API

#### GET /api/dashboard/overview
获取仪表板概览数据

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total_recordings": 317,
    "total_recognized": 0,
    "active_channels": 2,
    "today_recordings": 0,
    "recognition_rate": 0.0,
    "top_users": [...]
  }
}
```

#### GET /api/dashboard/trends
获取录音趋势数据

**查询参数**:
- `days`: 天数（默认: 7）

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "daily": [
      {"date": "2026-03-01", "count": 189, "recognized": 45},
      ...
    ]
  }
}
```

### 纠错规则 API

#### GET /api/rules
获取规则列表

**查询参数**:
- `category`: 规则分类筛选
- `is_enabled`: 启用状态筛选
- `search`: 搜索关键词
- `page`: 页码
- `page_size`: 每页数量

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "rules": [...],
    "total": 39,
    "page": 1
  }
}
```

#### POST /api/rules
创建规则

**请求体**:
```json
{
  "name": "测试规则",
  "error_pattern": "错误文本",
  "correction": "正确文本",
  "category": "common",
  "is_enabled": true
}
```

#### PUT /api/rules/{rule_id}
更新规则

**请求体**:
```json
{
  "name": "更新后的规则",
  "correction": "更新后的正确文本"
}
```

### 推送服务 API

#### GET /api/push/services
获取推送服务列表

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "services": [...]
  }
}
```

#### POST /api/push/test
测试推送

**请求体**:
```json
{
  "service_id": 1,
  "message": "测试消息"
}
```

### 广播任务 API

#### GET /api/broadcast/tasks
获取广播任务列表

**查询参数**:
- `task_type`: 任务类型筛选 (audio/tts)
- `trigger_type`: 触发类型筛选 (manual/schedule/keyword)
- `is_enabled`: 启用状态筛选

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "tasks": [...],
    "total": 1
  }
}
```

### 音频库 API

#### GET /api/audio-library
获取音频列表

**查询参数**:
- `source_type`: 来源类型 (recording/upload/tts)

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "audio_files": [...],
    "total": 1
  }
}
```

### 机器人监控 API

#### GET /api/monitor/overview
获取系统概览

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "recordings_24h": 0,
    "today_recordings": 0,
    "active_channels_7d": 2,
    "system": {
      "cpu_percent": 5.6,
      "memory_percent": 86.1,
      "disk_percent": 87.8
    },
    "uptime": "3天 5小时 12分钟"
  }
}
```

#### POST /api/monitor/control
控制机器人

**请求体**:
```json
{
  "action": "start"
}
```

**可用操作**: `start`, `stop`, `restart`, `status`

---

## 部署指南

### 生产环境部署

#### 1. 系统要求

- **操作系统**: Linux (Ubuntu 20.04+ 推荐)
- **Python**: 3.8+
- **内存**: 最低 1GB，推荐 2GB+
- **磁盘**: 最低 5GB，推荐 20GB+
- **CPU**: 最低 1 核，推荐 2 核+

#### 2. 使用 Gunicorn 部署

**安装 Gunicorn**:
```bash
pip install gunicorn
```

**启动命令**:
```bash
gunicorn web_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile /var/log/bsht-bot/access.log \
  --error-logfile /var/log/bsht-bot/error.log
```

#### 3. 使用 Systemd 服务

创建服务文件 `/etc/systemd/system/bsht-bot.service`:

```ini
[Unit]
Description=BSHT Bot Web Service
After=network.target

[Service]
Type=notify
User=bsht-bot
Group=bsht-bot
WorkingDirectory=/opt/bsht-bot
Environment="PATH=/opt/bsht-bot/venv/bin"
ExecStart=/opt/bsht-bot/venv/bin/gunicorn web_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**启动服务**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bsht-bot
sudo systemctl start bsht-bot
sudo systemctl status bsht-bot
```

#### 4. 使用 Docker 部署

**Dockerfile**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["gunicorn", "web_server:app", "--bind", "0.0.0.0:8000"]
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./recordings:/app/recordings
    environment:
      - WEB_SECRET_KEY=${WEB_SECRET_KEY}
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - web
    restart: unless-stopped
```

**启动**:
```bash
docker-compose up -d
```

#### 5. 使用 Nginx 反向代理

**Nginx 配置** (`/etc/nginx/sites-available/bsht-bot`):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /opt/bsht-bot/src/web/static;
        expires 30d;
    }

    location /recordings {
        alias /opt/bsht-bot/recordings;
    }
}
```

---

## 开发指南

### 项目结构

```
bsht-bot-core/
├── src/
│   ├── api/                 # API 路由
│   │   ├── auth.py          # 认证 API
│   │   ├── recordings.py   # 录音 API
│   │   ├── dashboard.py    # 仪表板 API
│   │   ├── rules.py        # 规则 API
│   │   ├── push.py         # 推送 API
│   │   ├── broadcast.py    # 广播 API
│   │   ├── audio_library.py # 音频库 API
│   │   └── monitor.py      # 监控 API
│   ├── database.py         # 数据库封装
│   ├── services/           # 业务逻辑服务
│   │   └── auth_service.py
│   └── web/
│       ├── templates/      # Jinja2 模板
│       └── static/         # 静态文件
├── web_server.py          # FastAPI 应用入口
├── requirements.txt        # Python 依赖
└── .env                   # 环境配置
```

### 添加新的 API 端点

1. 在 `src/api/` 创建新的 API 文件
2. 定义路由和处理函数
3. 在 `web_server.py` 中注册路由

示例：
```python
# src/api/my_feature.py
from fastapi import APIRouter
from src.database import Database

router = APIRouter()

@router.get("/my-feature")
async def get_my_feature(db: Database = Depends(get_db)):
    # 实现逻辑
    return {"code": 0, "message": "success", "data": {}}
```

注册路由：
```python
# web_server.py
from src.api import my_feature
app.include_router(my_feature.router, prefix="/api", tags=["my_feature"])
```

### 添加新的页面

1. 在 `src/web/templates/` 创建新的 HTML 文件
2. 继承 `base.html` 模板
3. 在 `web_server.py` 添加路由

示例：
```html
<!-- src/web/templates/my_page.html -->
{% extends "base.html" %}

{% block title %}我的页面 - BSHT Bot{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <h1 class="text-3xl font-bold">我的页面</h1>
</div>
{% endblock %}
```

### 运行测试

**后端 API 测试**:
```bash
python test_all_features_no_proxy.py
```

**前端交互测试**:
```bash
python test_interactions.py
```

**性能分析**:
```bash
python performance_analysis.py
```

---

## 常见问题

### 1. 登录失败

**问题**: 无法使用 admin/admin123 登录

**解决**:
```bash
# 重置密码
python -c "
import bcrypt
from src.database import Database
import sqlite3

db = Database()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()

password_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
cursor.execute('UPDATE users SET password_hash = ? WHERE username = ?', (password_hash, 'admin'))
conn.commit()
conn.close()
print('密码已重置为 admin123')
"
```

### 2. 数据库连接错误

**问题**: SQLite 数据库锁定

**解决**:
```bash
# 检查是否有其他进程占用数据库
# Linux
lsof data/records.db

# Windows
handle data/records.db
```

### 3. 端口已被占用

**问题**: 8000 端口已被占用

**解决**:
```bash
# Linux
sudo lsof -i :8000 | kill -9 $(lsof -t -i :8000)

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### 4. 静态文件 404

**问题**: CSS/JS 文件无法加载

**解决**:
- 检查 `src/web/static/` 目录是否存在
- 检查 `web_server.py` 中的静态文件挂载路径

### 5. Session 丢失

**问题**: 频繁要求重新登录

**解决**:
```python
# 增加 Session 过期时间
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=86400*7  # 7 天
)
```

---

## 许可证

MIT License

---

**最后更新**: 2026-03-04
**版本**: 1.0.0
