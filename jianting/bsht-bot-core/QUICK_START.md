# BSHT Bot Web 平台 - 快速启动指南

## 📋 前置要求

- **Python**: 3.8 或更高版本
- **操作系统**: Windows / Linux / macOS
- **浏览器**: Chrome / Firefox / Edge (推荐 Chrome)

---

## 🚀 快速启动 (5 分钟)

### 1. 安装依赖

```bash
# 进入项目目录
cd D:\Desktop\源代码收集\wxd\jianting\bsht-bot-core

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# .env 文件已存在，无需修改
# 如需修改配置，编辑 .env 文件
```

**重要配置项** (.env 文件中已配置):
```bash
# BSHT 账号 (用于 Bot 功能)
BSHT_USERNAME=bswxd
BSHT_PASSWORD=BsWxd2026
BSHT_CHANNEL_ID=62793

# AI 识别 API (可选)
SILICONFLOW_API_KEY=sk-xxxxx

# Web 平台密钥 (Session 加密)
WEB_SECRET_KEY=bsht-bot-secret-key-change-in-production
```

### 3. 初始化数据库

```bash
# 方法一: 使用 Python 初始化
python -c "from src.database import Database; Database().init_db()"

# 方法二: 直接运行（如果数据库已存在会自动初始化）
python web_server.py
```

### 4. 启动 Web 服务器

```bash
# 方法一: 直接启动 (开发环境，热重载)
python web_server.py

# 方法二: 使用 uvicorn 启动 (推荐)
uvicorn web_server:app --host 0.0.0.0 --port 8000 --reload

# 方法三: 生产环境启动 (4 进程)
gunicorn web_server:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. 访问系统

打开浏览器访问:

```
http://localhost:8000
```

**默认登录账号**:
- 用户名: `admin`
- 密码: `admin123`

---

## 📂 项目结构

```
bsht-bot-core/
├── web_server.py          # Web 服务器入口 (启动这个)
├── requirements.txt        # Python 依赖
├── .env                    # 环境配置
├── data/                   # 数据目录
│   ├── records.db         # SQLite 数据库
│   └── audio_library/     # 音频库
├── recordings/             # 录音文件存储
├── src/
│   ├── api/               # API 路由
│   ├── database.py        # 数据库封装
│   └── web/
│       ├── templates/     # HTML 模板
│       └── static/        # 静态文件 (CSS/JS)
└── docs/                  # 文档
```

---

## 🎯 功能测试清单

### ✅ 基础功能

- [ ] 登录系统 (admin/admin123)
- [ ] 查看仪表板统计
- [ ] 查看录音列表
- [ ] 播放录音文件
- [ ] 查看语音识别结果

### ✅ 录音管理

- [ ] 筛选录音 (按用户/频道/日期)
- [ ] 搜索录音关键词
- [ ] 删除录音
- [ ] 查看录音统计

### ✅ 纠错规则

- [ ] 查看规则列表
- [ ] 创建新规则
- [ ] 编辑规则
- [ ] 启用/禁用规则
- [ ] 删除规则

### ✅ 推送服务

- [ ] 查看推送服务配置
- [ ] 测试推送功能
- [ ] 查看推送历史

### ✅ 广播任务

- [ ] 查看广播任务列表
- [ ] 创建广播任务
- [ ] 上传音频文件
- [ ] 使用 TTS 功能
- [ ] 执行/停止任务

### ✅ 系统监控

- [ ] 查看系统资源使用
- [ ] 查看录音趋势图表
- [ ] 控制机器人 (启动/停止)
- [ ] 查看实时日志

---

## 🔧 常见问题

### 1. 端口被占用

**问题**: 8000 端口已被使用

**解决**:
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :8000
kill -9 <PID>
```

或者使用其他端口:
```bash
uvicorn web_server:app --port 8001
```

### 2. 登录失败

**问题**: 无法使用 admin/admin123 登录

**解决**:
```bash
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

### 3. 数据库错误

**问题**: SQLite 数据库锁定

**解决**:
```bash
# Windows
handle data/records.db

# Linux/macOS
lsof data/records.db
```

### 4. 静态文件 404

**问题**: CSS/JS 文件无法加载

**解决**: 检查以下目录是否存在:
```bash
src/web/static/
recordings/
data/audio_library/
```

### 5. 依赖安装失败

**问题**: pip install 失败

**解决**:
```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 📊 系统监控

启动后访问以下地址:

- **主页**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs (Swagger UI)
- **仪表板**: http://localhost:8000/dashboard
- **录音管理**: http://localhost:8000/recordings
- **纠错规则**: http://localhost:8000/rules
- **推送服务**: http://localhost:8000/push
- **广播任务**: http://localhost:8000/broadcast
- **系统监控**: http://localhost:8000/monitor

---

## 🎨 开发模式

### 启用热重载

```bash
uvicorn web_server:app --reload --log-level debug
```

### 查看日志

```bash
# 实时查看日志
tail -f log/bot.log

# Windows
Get-Content log/bot.log -Wait
```

### 测试 API

```bash
# 使用 curl 测试登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"admin123\"}"
```

---

## 🚀 生产环境部署

如需部署到生产环境，请参考:

- **完整部署指南**: [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)
- **API 文档**: [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)

**快速部署**:
```bash
# 使用 Gunicorn (4 进程)
gunicorn web_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile log/access.log \
  --error-logfile log/error.log
```

---

## 📞 技术支持

如遇问题，请检查:

1. **Python 版本**: `python --version` (需要 3.8+)
2. **依赖安装**: `pip list | grep fastapi`
3. **数据库文件**: `ls -lh data/records.db`
4. **端口占用**: `netstat -an | grep 8000`
5. **日志文件**: `cat log/bot.log`

---

**最后更新**: 2026-03-04
**版本**: 1.0.0
