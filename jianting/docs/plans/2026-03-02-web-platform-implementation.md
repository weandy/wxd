# Web 管理平台实施计划

> **项目**: BSHT Bot - Web 管理平台
> **设计文档**: [2026-03-02-web-platform-design.md](./2026-03-02-web-platform-design.md)
> **创建日期**: 2026-03-02

---

## 📋 总览

本实施计划将设计方案分解为可执行的开发任务，按优先级和依赖关系排序。

**预计总时间**: 12-16 天

---

## Phase 1: 基础设施与认证 (3-4 天)

### 1.1 项目结构搭建
**文件**: `web_server.py`, `src/api/__init__.py`, `src/web/`

- [ ] 创建 `web_server.py` - FastAPI 应用入口
- [ ] 创建 API 模块目录 `src/api/`
- [ ] 创建前端资源目录 `src/web/`
- [ ] 配置 Tailwind CSS CDN
- [ ] 创建基础模板 `src/web/templates/base.html`

**验收标准**:
- 访问 `http://localhost:8000` 显示基础页面
- 静态文件可访问

---

### 1.2 数据库扩展
**文件**: `src/database.py`

- [ ] 添加 `users` 表
- [ ] 添加 `correction_rules` 表
- [ ] 添加 `broadcast_tasks` 表
- [ ] 添加 `audio_library` 表
- [ ] 创建数据库迁移函数
- [ ] 迁移现有 prompts.md 到 correction_rules 表
- [ ] 创建默认管理员账户

**验收标准**:
- 数据库表创建成功
- 默认 admin 账户可登录
- prompts.md 规则已迁移

---

### 1.3 认证系统
**文件**: `src/api/auth.py`, `src/services/auth_service.py`

- [ ] 实现 `/api/auth/login` - 登录接口
- [ ] 实现 `/api/auth/logout` - 登出接口
- [ ] 实现 `/api/auth/me` - 获取当前用户
- [ ] Session 中间件（验证 Cookie）
- [ ] 密码哈希（bcrypt）
- [ ] 创建登录页面 `login.html`

**验收标准**:
- 用户可登录/登出
- 未登录访问受保护页面返回 401
- Session 24 小时过期

---

## Phase 2: 录音管理 (2-3 天)

### 2.1 录音列表 API
**文件**: `src/api/recordings.py`

- [ ] 实现 `GET /api/recordings` - 获取录音列表（分页、筛选）
- [ ] 实现 `GET /api/recordings/{id}` - 获取单个录音详情
- [ ] 实现 `GET /api/recordings/dates` - 获取有录音的日期列表
- [ ] 音频文件访问控制 `GET /audio/{path}`

**验收标准**:
- API 返回正确格式的数据
- 分页功能正常
- 筛选功能（日期、用户）正常

---

### 2.2 录音列表页面
**文件**: `src/web/templates/recordings.html`, `src/web/static/js/recordings.js`

- [ ] 创建录音列表页面布局
- [ ] 实现日期筛选下拉框
- [ ] 实现用户筛选下拉框
- [ ] 实现搜索框
- [ ] 实现刷新按钮
- [ ] 实现录音列表表格（播放、时间、用户、时长、识别文本）
- [ ] 实现分页控制

**验收标准**:
- 页面正确显示录音列表
- 播放按钮可播放音频
- 筛选和搜索功能正常

---

## Phase 3: 统计仪表盘 (2-3 天)

### 3.1 统计数据 API
**文件**: `src/api/dashboard.py`

- [ ] 实现 `GET /api/dashboard/overview` - 概览数据
- [ ] 实现 `GET /api/dashboard/trend` - 7天趋势
- [ ] 实现 `GET /api/dashboard/signal-types` - 信号类型分布
- [ ] 实现 `GET /api/dashboard/top-users` - 活跃用户排行

**验收标准**:
- API 返回统计数据
- 数据计算准确

---

### 3.2 仪表盘页面
**文件**: `src/web/templates/dashboard.html`, `src/web/static/js/dashboard.js`

- [ ] 创建仪表盘页面布局
- [ ] 实现概览卡片（录音数、增长率、活跃用户、总时长）
- [ ] 实现识别率趋势图（使用 Chart.js）
- [ ] 实现信号类型分布饼图
- [ ] 实现活跃用户排行榜

**验收标准**:
- 页面正确显示统计数据
- 图表渲染正确
- 数据实时更新（手动刷新）

---

## Phase 4: 纠错规则管理 (2 天)

### 4.1 规则管理 API
**文件**: `src/api/rules.py`

- [ ] 实现 `GET /api/rules` - 获取规则列表
- [ ] 实现 `POST /api/rules` - 创建规则
- [ ] 实现 `PUT /api/rules/{id}` - 更新规则
- [ ] 实现 `DELETE /api/rules/{id}` - 删除规则
- [ ] 实现 `POST /api/rules/test` - 测试规则效果

**验收标准**:
- CRUD 功能正常
- 规则测试返回正确结果

---

### 4.2 规则管理页面
**文件**: `src/web/templates/rules.html`

- [ ] 创建规则管理页面布局
- [ ] 实现规则列表（显示模式、类型、状态）
- [ ] 实现规则编辑弹窗
- [ ] 实现规则测试预览功能
- [ ] 实现启用/禁用切换

**验收标准**:
- 可正常增删改查规则
- 规则测试显示正确结果

---

## Phase 5: 推送服务管理 (1-2 天)

### 5.1 推送服务 API
**文件**: `src/api/push.py`

- [ ] 实现 `GET /api/push/services` - 获取推送服务
- [ ] 实现 `PUT /api/push/services/{id}` - 更新推送服务
- [ ] 实现 `GET /api/push/targets` - 获取推送目标
- [ ] 实现 `POST /api/push/targets` - 添加推送目标
- [ ] 实现 `PUT /api/push/targets/{id}` - 更新推送目标
- [ ] 实现 `DELETE /api/push/targets/{id}` - 删除推送目标
- [ ] 实现 `POST /api/push/test` - 测试推送

**验收标准**:
- 可正常管理推送目标和关键词
- 测试推送功能正常

---

### 5.2 推送服务页面
**文件**: `src/web/templates/push.html`

- [ ] 创建推送服务页面布局
- [ ] 实现推送服务配置显示
- [ ] 实现推送目标列表
- [ ] 实现添加/编辑/删除推送目标

**验收标准**:
- 可正常管理推送配置
- 无需修改 .env 文件

---

## Phase 6: 广播任务与音频库 (3-4 天)

### 6.1 广播任务 API
**文件**: `src/api/broadcast.py`, `src/services/broadcast_service.py`

- [ ] 实现 `GET /api/broadcast/tasks` - 获取任务列表
- [ ] 实现 `POST /api/broadcast/tasks` - 创建任务
- [ ] 实现 `PUT /api/broadcast/tasks/{id}` - 更新任务
- [ ] 实现 `DELETE /api/broadcast/tasks/{id}` - 删除任务
- [ ] 实现 `POST /api/broadcast/tasks/{id}/execute` - 立即执行
- [ ] 实现 APScheduler 任务调度
- [ ] 实现 Bot PTT 控制接口

**验收标准**:
- 任务 CRUD 功能正常
- 定时任务按时执行

---

### 6.2 音频库 API
**文件**: `src/api/broadcast.py`

- [ ] 实现 `GET /api/broadcast/audio` - 获取音频库
- [ ] 实现 `POST /api/broadcast/audio/tts` - TTS 生成
- [ ] 实现 `POST /api/broadcast/audio/upload` - 上传音频
- [ ] 实现 `DELETE /api/broadcast/audio/{id}` - 删除音频
- [ ] 集成 edge-tts 或其他 TTS 服务

**验收标准**:
- 可正常上传音频
- TTS 生成功能正常

---

### 6.3 广播任务页面
**文件**: `src/web/templates/broadcast.html`, `src/web/static/js/broadcast.js`

- [ ] 创建广播任务页面布局
- [ ] 实现任务列表
- [ ] 实现任务编辑弹窗
- [ ] 实现音频库显示
- [ ] 实现 TTS 生成面板
- [ ] 实现音频上传功能
- [ ] 实现音频播放试听

**验收标准**:
- 可正常管理广播任务
- 可使用 TTS 生成音频
- 可上传和管理音频文件

---

## Phase 7: Bot 监控 (2 天)

### 7.1 监控 API
**文件**: `src/api/monitor.py`

- [ ] 实现 `GET /api/monitor/status` - Bot 状态
- [ ] 实现 `GET /api/monitor/channel` - 当前频道
- [ ] 实现 `GET /api/monitor/audio-stream` - 音频流数据
- [ ] 实现 `GET /api/monitor/activities` - 活动日志
- [ ] 实现 `POST /api/monitor/control` - Bot 控制
- [ ] 实现 Bot 状态共享机制（SQLite/共享内存）

**验收标准**:
- API 正确返回 Bot 状态
- Bot 控制功能正常

---

### 7.2 监控页面
**文件**: `src/web/templates/monitor.html`, `src/web/static/js/monitor.js`

- [ ] 创建监控页面布局
- [ ] 实现 Bot 状态显示
- [ ] 实现当前频道信息
- [ ] 实现实时音频流数据
- [ ] 实现活动日志（5秒自动刷新）
- [ ] 实现 Bot 控制按钮

**验收标准**:
- 页面正确显示 Bot 状态
- 活动日志自动更新

---

## Phase 8: 测试与优化 (2 天)

### 8.1 功能测试

- [ ] 所有功能端到端测试
- [ ] 多用户并发测试
- [ ] 音频播放兼容性测试
- [ ] 浏览器兼容性测试

### 8.2 性能优化

- [ ] 数据库查询优化
- [ ] 静态资源缓存
- [ ] API 响应时间优化

### 8.3 安全加固

- [ ] SQL 注入测试
- [ ] XSS 防护测试
- [ ] CSRF 防护测试
- [ ] 文件访问权限测试

### 8.4 部署准备

- [ ] 编写部署文档
- [ ] 配置 Systemd 服务
- [ ] Nginx 反向代理配置

---

## 📊 进度跟踪

| Phase | 任务 | 状态 | 负责人 | 完成日期 |
|-------|------|------|--------|----------|
| 1.1 | 项目结构搭建 | ⏳ 待开始 | | |
| 1.2 | 数据库扩展 | ⏳ 待开始 | | |
| 1.3 | 认证系统 | ⏳ 待开始 | | |
| 2.1 | 录音列表 API | ⏳ 待开始 | | |
| 2.2 | 录音列表页面 | ⏳ 待开始 | | |
| 3.1 | 统计数据 API | ⏳ 待开始 | | |
| 3.2 | 仪表盘页面 | ⏳ 待开始 | | |
| 4.1 | 规则管理 API | ⏳ 待开始 | | |
| 4.2 | 规则管理页面 | ⏳ 待开始 | | |
| 5.1 | 推送服务 API | ⏳ 待开始 | | |
| 5.2 | 推送服务页面 | ⏳ 待开始 | | |
| 6.1 | 广播任务 API | ⏳ 待开始 | | |
| 6.2 | 音频库 API | ⏳ 待开始 | | |
| 6.3 | 广播任务页面 | ⏳ 待开始 | | |
| 7.1 | 监控 API | ⏳ 待开始 | | |
| 7.2 | 监控页面 | ⏳ 待开始 | | |
| 8.1 | 功能测试 | ⏳ 待开始 | | |
| 8.2 | 性能优化 | ⏳ 待开始 | | |
| 8.3 | 安全加固 | ⏳ 待开始 | | |
| 8.4 | 部署准备 | ⏳ 待开始 | | |

---

## 🔧 技术依赖

### Python 包
```txt
fastapi>=0.104.0
uvicorn>=0.24.0
jinja2>=3.1.2
python-multipart>=0.0.6
bcrypt>=4.0.1
apscheduler>=3.10.0
edge-tts>=6.1.0
aiofiles>=23.2.1
```

### 前端库
- Tailwind CSS (CDN)
- Chart.js (CDN)

---

## 📝 注意事项

1. **保留多频道扩展性**: 数据库设计已预留 channel_id，代码中注意兼容
2. **音频文件安全**: 所有音频访问需验证用户登录
3. **密码安全**: 使用 bcrypt 哈希，不存储明文密码
4. **SQL 注入防护**: 使用参数化查询
5. **向后兼容**: 不影响现有 Bot 功能

---

**文档版本**: 1.0
**最后更新**: 2026-03-02
**状态**: ⏳ 准备实施
