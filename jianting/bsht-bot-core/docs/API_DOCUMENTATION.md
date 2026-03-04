# BSHT Bot Web 平台 - API 完整文档

## 基础信息

- **Base URL**: `http://localhost:8000` (开发环境)
- **认证方式**: Session Cookie
- **数据格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

### 成功响应
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 错误响应
```json
{
  "code": 400,
  "message": "错误描述",
  "detail": "详细错误信息"
}
```

---

## 认证 API

### POST /api/auth/login
**功能**: 用户登录

**请求头**:
```
Content-Type: application/json
```

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

### POST /api/auth/logout
**功能**: 用户登出

**请求头**:
```
Cookie: session_id=<session_token>
```

**响应**:
```json
{
  "code": 0,
  "message": "success"
}
```

### GET /api/auth/me
**功能**: 获取当前登录用户信息

**请求头**:
```
Cookie: session_id=<session_token>
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

---

## 录音管理 API

### GET /api/recordings
**功能**: 获取录音列表（支持分页和筛选）

**请求头**:
```
Cookie: session_id=<session_token>
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20 |
| channel_id | str | 否 | 频道ID筛选 |
| user_id | str | 否 | 用户ID筛选 |
| recognized | int | 否 | 识别状态筛选 (0=未识别, 1=已识别) |
| start_date | str | 否 | 开始日期 (YYYY-MM-DD) |
| end_date | str | 否 | 结束日期 (YYYY-MM-DD) |
| search | str | 否 | 搜索关键词 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "filepath": "/recordings/xxx.opus",
        "filename": "recording_001.opus",
        "channel_id": "123456",
        "user_id": "789",
        "user_name": "张三",
        "recorder_type": "RX",
        "duration": 120.5,
        "start_time": "2026-03-04T10:30:00",
        "file_size": 12345,
        "recognized": true,
        "asr_text": "识别的文本"
      }
    ],
    "total": 317,
    "page": 1,
    "page_size": 20,
    "total_pages": 16
  }
}
```

### GET /api/recordings/{recording_id}
**功能**: 获取单个录音详情

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "filepath": "/recordings/xxx.opus",
    "filename": "recording_001.opus",
    "channel_id": "123456",
    "user_id": "789",
    "duration": 120.5
  }
}
```

### DELETE /api/recordings/{recording_id}
**功能**: 删除录音

**响应**:
```json
{
  "code": 0,
  "message": "删除成功",
  "data": {"id": 1}
}
```

### GET /api/recordings/stats
**功能**: 获取录音统计

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 317,
    "today": 0,
    "recent_24h": 0,
    "recognized": 0,
    "total_duration_minutes": 15234.5,
    "avg_duration": 48.0,
    "recognition_rate": 0.0
  }
}
```

---

## 仪表板 API

### GET /api/dashboard/overview
**功能**: 获取仪表板概览数据

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
    "yesterday_recordings": 0,
    "growth_rate": 0.0,
    "recognition_rate": 0.0,
    "total_users": 10,
    "active_users_7d": 5
  }
}
```

### GET /api/dashboard/trends
**功能**: 获取录音趋势数据

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| days | int | 否 | 天数，默认 7 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "daily": [
      {
        "date": "2026-03-01",
        "count": 189,
        "recognized": 45,
        "rate": 23.8
      }
    ]
  }
}
```

---

## 纠错规则 API

### GET /api/rules
**功能**: 获取纠错规则列表

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | str | 否 | 规则分类 |
| is_enabled | bool | 否 | 启用状态 |
| search | str | 否 | 搜索关键词 |
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "rules": [
      {
        "id": 1,
        "name": "测试规则",
        "error_pattern": "错误文本",
        "correction": "正确文本",
        "category": "common",
        "is_enabled": true,
        "match_count": 10,
        "created_at": "2026-03-01T10:00:00"
      }
    ],
    "total": 39,
    "page": 1,
    "page_size": 20
  }
}
```

### POST /api/rules
**功能**: 创建纠错规则

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

**响应**:
```json
{
  "code": 0,
  "message": "创建成功",
  "data": {"id": 40}
}
```

### PUT /api/rules/{rule_id}
**功能**: 更新纠错规则

**请求体**:
```json
{
  "name": "更新后的规则名称",
  "correction": "更新后的正确文本",
  "is_enabled": false
}
```

### DELETE /api/rules/{rule_id}
**功能**: 删除纠错规则

### POST /api/rules/{rule_id}/toggle
**功能**: 切换规则启用状态

---

## 监控 API

### GET /api/monitor/overview
**功能**: 获取系统概览

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
      "memory_used_gb": 13.5,
      "memory_total_gb": 15.7,
      "disk_used_gb": 200.5,
      "disk_total_gb": 228.5,
      "disk_percent": 87.8
    },
    "uptime": "3天 5小时"
  }
}
```

### POST /api/monitor/control
**功能**: 控制机器人

**请求体**:
```json
{
  "action": "start"
}
```

**可用操作**:
- `start`: 启动机器人
- `stop`: 停止机器人
- `restart`: 重启机器人
- `status`: 查看状态

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "running": true,
    "pid": 12345,
    "uptime": "2026-03-04T08:00:00"
  }
}
```

---

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未登录 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

---

## 速率限制

当前版本未实现速率限制，建议在生产环境中使用 Nginx 配置。

---

## 更新日志

### v1.0.0 (2026-03-04)
- 初始版本
- 完成所有 7 个开发阶段
- 提供完整的 API 接口
