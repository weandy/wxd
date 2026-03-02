# Web 管理平台设计方案

> **项目**: BSHT Bot - Web 管理平台
> **日期**: 2026-03-02
> **状态**: ✅ 已批准

---

## 1. 项目概述

### 1.1 目标
为 BSHT Bot Core 添加 Web 管理平台，实现团队共享访问，支持：
- 录音文件查看与播放
- 语音识别结果查看
- 纠错规则管理
- 推送服务管理
- 数据统计分析
- 定时广播任务（含 TTS 和实时录制）
- Bot 运行监控

### 1.2 使用场景
- **团队共享**: 多个业余无线电团队成员同时访问
- **轻量级部署**: FastAPI + 纯 HTML/JS/CSS，无复杂框架
- **手动刷新**: 用户手动刷新更新数据，无需实时推送

### 1.3 技术栈
| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn |
| 前端 | 纯 HTML + Tailwind CSS (CDN) + Vanilla JS |
| 数据库 | SQLite (扩展现有 records.db) |
| 认证 | Session Cookie + bcrypt |

---

## 2. 整体架构

### 2.1 单体服务方案

```
┌─────────────────────────────────────────────┐
│              FastAPI Web 服务               │
│  ┌───────────────────────────────────────┐  │
│  │            API 路由                    │  │
│  │  /api/auth      /api/recordings        │  │
│  │  /api/rules     /api/push              │  │
│  │  /api/broadcast /api/dashboard         │  │
│  │  /api/monitor                         │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │            静态文件                    │  │
│  │  /templates/    /static/              │  │
│  │  /recordings/   /audio_library/       │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
         │              │
         ▼              ▼
    SQLite         录音文件目录
```

### 2.2 目录结构

```
bsht-bot-core/
├── web_server.py              # 新增：Web 服务入口
├── bot_server.py              # 现有：Bot 服务
├── run_all.py                 # 修改：同时启动 Bot + Web
│
├── src/
│   ├── database.py            # 修改：添加新表
│   ├── api/                   # 新增：API 模块
│   │   ├── auth.py
│   │   ├── recordings.py
│   │   ├── rules.py
│   │   ├── push.py
│   │   ├── broadcast.py
│   │   ├── dashboard.py
│   │   └── monitor.py
│   ├── services/              # 新增：业务逻辑层
│   │   ├── auth_service.py
│   │   ├── rule_service.py
│   │   ├── broadcast_service.py
│   │   └── tts_service.py
│   └── web/                   # 新增：前端资源
│       ├── static/
│       │   ├── css/style.css
│       │   └── js/
│       └── templates/
│           ├── base.html
│           ├── login.html
│           ├── dashboard.html
│           ├── recordings.html
│           ├── rules.html
│           ├── push.html
│           ├── broadcast.html
│           └── monitor.html
│
├── data/
│   ├── records.db
│   └── audio_library/         # 新增：广播音频库
└── recordings/                # 现有：频道录音
```

---

## 3. 数据库设计

### 3.1 新增表结构

#### 用户表 (users)
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname TEXT,
    role TEXT DEFAULT 'user',  -- admin / user
    created_at TEXT NOT NULL,
    last_login TEXT,
    is_active BOOLEAN DEFAULT 1
);
```

#### 纠错规则表 (correction_rules)
```sql
CREATE TABLE correction_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL,  -- 'replace' / 'preserve' / 'regex'
    pattern TEXT NOT NULL,
    replacement TEXT,
    description TEXT,
    category TEXT,             -- 'must_replace' / 'preserve' / 'custom'
    priority INTEGER DEFAULT 0,
    is_enabled BOOLEAN DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

#### 广播任务表 (broadcast_tasks)
```sql
CREATE TABLE broadcast_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,   -- 'scheduled' / 'event_triggered'
    trigger_type TEXT,         -- 'hourly' / 'daily' / 'user_join'
    trigger_config TEXT,       -- JSON: {"minute": 0}
    content_type TEXT NOT NULL, -- 'tts' / 'audio_file'
    audio_file_id INTEGER,     -- 关联 audio_library.id
    tts_text TEXT,             -- TTS 文字内容
    tts_config TEXT,           -- JSON: {"voice": "default", "speed": 1.0}
    is_enabled BOOLEAN DEFAULT 1,
    last_executed TEXT,
    execution_count INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (audio_file_id) REFERENCES audio_library(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

#### 音频库表 (audio_library)
```sql
CREATE TABLE audio_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- 'tts' / 'upload' / 'record'
    description TEXT,
    duration REAL,
    file_size INTEGER,
    metadata TEXT,              -- JSON: 扩展信息
    created_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

### 3.2 默认数据

#### 默认管理员
```
用户名: admin
密码: admin
角色: admin
```

#### 纠错规则初始数据
从 `src/prompts.md` 迁移：
- "必须替换" → `rule_type='replace', category='must_replace'`
- "保留原文" → `rule_type='preserve', category='preserve'`

---

## 4. API 设计

### 4.1 认证 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/logout` | 用户登出 |
| GET | `/api/auth/me` | 获取当前用户信息 |

### 4.2 录音 API

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/recordings` | 获取录音列表 | `?page=1&date=2026-03-02&user_id=xxx` |
| GET | `/api/recordings/{id}` | 获取单个录音详情 | - |
| GET | `/api/recordings/dates` | 获取有录音的日期列表 | - |
| GET | `/audio/{path}` | 播放录音文件 | - |

### 4.3 纠错规则 API

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/rules` | 获取规则列表 | `?category=all` |
| POST | `/api/rules` | 创建规则 | Body: JSON |
| PUT | `/api/rules/{id}` | 更新规则 | Body: JSON |
| DELETE | `/api/rules/{id}` | 删除规则 | - |
| POST | `/api/rules/test` | 测试规则效果 | Body: `{text, rules}` |

### 4.4 推送服务 API

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/push/services` | 获取推送服务列表 | - |
| PUT | `/api/push/services/{id}` | 更新推送服务 | Body: JSON |
| GET | `/api/push/targets` | 获取推送目标列表 | - |
| POST | `/api/push/targets` | 添加推送目标 | Body: JSON |
| PUT | `/api/push/targets/{id}` | 更新推送目标 | Body: JSON |
| DELETE | `/api/push/targets/{id}` | 删除推送目标 | - |
| POST | `/api/push/test` | 测试推送 | Body: `{target_id, message}` |

### 4.5 广播任务 API

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/broadcast/tasks` | 获取任务列表 | - |
| POST | `/api/broadcast/tasks` | 创建任务 | Body: JSON |
| PUT | `/api/broadcast/tasks/{id}` | 更新任务 | Body: JSON |
| DELETE | `/api/broadcast/tasks/{id}` | 删除任务 | - |
| POST | `/api/broadcast/tasks/{id}/execute` | 立即执行任务 | - |
| GET | `/api/broadcast/audio` | 获取音频库 | - |
| POST | `/api/broadcast/audio/tts` | TTS 生成音频 | Body: JSON |
| POST | `/api/broadcast/audio/upload` | 上传音频 | Form: file |
| POST | `/api/broadcast/audio/record` | 实时录制音频 | Body: Blob |

### 4.6 统计数据 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/overview` | 获取概览数据 |
| GET | `/api/dashboard/trend` | 获取趋势数据（7天） |
| GET | `/api/dashboard/signal-types` | 获取信号类型分布 |
| GET | `/api/dashboard/top-users` | 获取活跃用户排行 |

### 4.7 Bot 监控 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/monitor/status` | 获取 Bot 状态 |
| GET | `/api/monitor/channel` | 获取当前频道信息 |
| GET | `/api/monitor/audio-stream` | 获取实时音频流数据 |
| GET | `/api/monitor/activities` | 获取最近活动日志 |
| POST | `/api/monitor/control` | 控制 Bot (暂停/恢复/停止) |

---

## 5. 前端页面设计

### 5.1 页面列表（9个）

| # | 页面 | 文件 | 功能 |
|---|------|------|------|
| 1 | 登录页 | login.html | 用户认证 |
| 2 | 统计仪表盘 | dashboard.html | 数据统计、图表分析 |
| 3 | 录音列表 | recordings.html | 查看/播放录音、识别结果 |
| 4 | 纠错规则 | rules.html | 规则管理、测试预览 |
| 5 | 推送服务 | push.html | 推送目标和关键词管理 |
| 6 | 广播任务 | broadcast.html | 定时任务、音频库管理 |
| 7 | Bot 监控 | monitor.html | 实时状态、活动日志 |

### 5.2 页面布局说明

#### 登录页 (login.html)
- 简单的居中登录表单
- 用户名/密码输入框

#### 统计仪表盘 (dashboard.html)
- 今日概览卡片（录音数、增长率、活跃用户、总时长）
- 识别率趋势图（7天）
- 信号类型分布饼图
- 活跃用户排行榜

#### 录音列表 (recordings.html)
- 日期筛选、用户筛选
- 搜索框、刷新按钮
- 录音列表（播放按钮、时间、用户、时长、识别文本）
- 分页控制

#### 纠错规则 (rules.html)
- 规则分类/状态筛选
- 规则列表（显示模式、类型、状态）
- 新增/编辑/删除/启用/禁用操作
- 规则测试预览

#### 推送服务 (push.html)
- 推送服务配置显示
- 推送目标列表（用户ID、名称、关键词）
- 新增/编辑/删除推送目标

#### 广播任务 (broadcast.html)
- 任务列表（名称、类型、频率、状态）
- 新建/编辑/删除/立即执行任务
- 音频库管理：
  - TTS 生成
  - 上传音频
  - 实时录制

#### Bot 监控 (monitor.html)
- Bot 运行状态（PID、运行时长）
- 当前频道信息
- 实时音频流数据
- 最近活动日志（自动刷新）
- Bot 控制按钮（暂停/恢复/停止）

---

## 6. 认证与安全

### 6.1 认证流程

```
用户输入账号密码
       │
       ▼
POST /api/auth/login
       │
       ▼
服务端验证 → 生成 Session Token
       │
       ▼
返回 Cookie: session_token=xxx
       │
       ▼
后续请求自动携带 Cookie
       │
       ▼
服务端验证 Token → 返回数据
```

### 6.2 安全措施

| 措施 | 实现方式 |
|------|----------|
| 密码哈希 | bcrypt 存储密码 |
| Session 过期 | 24 小时自动过期 |
| CSRF 保护 | 验证 Referer |
| SQL 注入防护 | 参数化查询 |
| 路径遍历防护 | 验证文件路径合法性 |
| 音频文件保护 | 需登录才能访问 `/audio/*` |

### 6.3 权限设计

| 角色 | 权限 |
|------|------|
| admin | 所有功能 |
| user | 查看录音、规则、监控（不可编辑） |

---

## 7. 技术实现要点

### 7.1 后端实现

**Web 服务入口 (web_server.py):**
```python
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# 挂载静态文件
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
app.mount("/recordings", StaticFiles(directory="recordings"), name="recordings")
app.mount("/audio_library", StaticFiles(directory="data/audio_library"), name="audio_library")

# 模板
templates = Jinja2Templates(directory="src/web/templates")

# 路由
from src.api import auth, recordings, rules, push, broadcast, dashboard, monitor
app.include_router(auth.router)
app.include_router(recordings.router)
app.include_router(rules.router)
app.include_router(push.router)
app.include_router(broadcast.router)
app.include_router(dashboard.router)
app.include_router(monitor.router)
```

### 7.2 前端实现

**使用 Tailwind CSS (CDN):**
```html
<script src="https://cdn.tailwindcss.com"></script>
```

**JavaScript 模块化:**
```javascript
// src/web/static/js/app.js
const API_BASE = '/api';

async function fetchAPI(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  return await response.json();
}
```

### 7.3 TTS 集成

**TTS 服务建议:**
- Azure Cognitive Services
- 讯飞语音
- 百度语音
- edge-tts（免费，推荐）

### 7.4 广播任务调度

**使用 APScheduler:**
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# 每小时报时
scheduler.add_job(
    execute_broadcast_task,
    'cron',
    minute=0,
    id='hourly_chime'
)
```

---

## 8. 部署方式

### 8.1 开发环境

```bash
# 启动 Web 服务
python web_server.py

# 或同时启动 Bot + Web
python run_all.py
```

访问: `http://localhost:8000`

### 8.2 生产环境

**使用 Systemd 服务:**
```ini
[Unit]
Description=BSHT Bot Web Service
After=network.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/bsht-bot-core
ExecStart=/usr/bin/python3 web_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**使用 Nginx 反向代理:**
```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 9. 未来扩展

### 9.1 多频道支持

数据库设计已预留 `channel_id` 字段，未来可扩展：
- 频道管理页面
- 按频道筛选数据
- 多频道 Bot 切换

### 9.2 实时推送

可选升级为 WebSocket 实时推送：
- 新录音实时通知
- Bot 状态实时更新
- 在线用户协作

---

## 10. 开发计划

| 阶段 | 功能 | 预计时间 |
|------|------|----------|
| Phase 1 | 用户认证、录音列表 | 3-4 天 |
| Phase 2 | 统计仪表盘、纠错规则 | 2-3 天 |
| Phase 3 | 推送服务、Bot 监控 | 2 天 |
| Phase 4 | 广播任务、音频库、TTS | 3-4 天 |
| Phase 5 | 测试、优化、部署 | 2 天 |

**总计**: 约 12-16 天

---

## 附录：决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 架构方案 | 单体服务 | 轻量级、快速开发 |
| 前端框架 | 纯 HTML/JS | 无框架依赖、易维护 |
| 认证方式 | Session Cookie | 简单够用 |
| 实时性 | 手动刷新 | 降低复杂度 |
| TTS 集成 | 音频库内功能 | 统一管理 |

---

**文档版本**: 1.0
**最后更新**: 2026-03-02
**状态**: ✅ 已批准，准备实施
