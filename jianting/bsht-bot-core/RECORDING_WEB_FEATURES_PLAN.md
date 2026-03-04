# 录音存档 Web 功能增强实施计划

> 创建时间: 2026-03-04
> 状态: 规划中

## 项目概述

为 BSHT Bot Web 平台增强录音存档相关功能，实现实时查看录音文件、在线播放、语音转文字结果显示和纠错规则管理。

## 当前项目状态分析

### 已有功能
- ✅ 完整的数据库表结构 (recordings, audio_records, correction_rules)
- ✅ FastAPI Web 服务器 (web_server.py)
- ✅ 录音 API (src/api/recordings.py) - 基础列表功能
- ✅ 规则管理 API (src/api/rules.py)
- ✅ 用户认证系统 (src/api/auth.py)
- ✅ 静态文件挂载 (/recordings, /audio_library)

### 录音文件存储结构
```
recordings/
├── 2026-03-04/
│   ├── 001_822340024_093321.wav
│   ├── 002_822340024_094310.wav
│   └── conversation_log.json
├── 2026-03-03/
│   └── ...
```

### 数据库关键字段
- **recordings 表**: filepath, filename, user_id, user_name, duration, asr_text, content_normalized, signal_type, confidence, rms_db, snr_db
- **correction_rules 表**: name, rule_type, pattern, replacement, category, is_enabled

---

## 功能需求分解

### 1. 实时录音列表查看

**需求描述**: 用户可以按日期、用户、频道筛选录音，实时查看录音列表

**实施步骤**:
1. 增强 `/api/recordings` API
   - 添加分页支持
   - 添加排序选项
   - 添加更多筛选条件（日期范围、信号类型）
2. 创建实时统计 API
   - 今日录音数量
   - 今日录音总时长
   - 各用户录音统计
3. 前端页面优化
   - 添加高级筛选面板
   - 添加统计卡片
   - 优化列表展示

**文件变更**:
- `src/api/recordings.py` - 增强 API
- `src/web/templates/recordings.html` - 前端页面
- `src/web/static/js/recordings.js` - 前端逻辑

---

### 2. 在线音频播放

**需求描述**: 用户可以直接在网页上播放录音文件

**实施步骤**:
1. 创建音频播放组件
   - HTML5 Audio 元素
   - 播放控制（播放/暂停、进度条、音量）
   - 播放速度调节
2. 添加播放列表功能
   - 连续播放
   - 自动播放下一条
3. 添加波形显示（可选）
   - 使用 Web Audio API
   - 显示音频波形

**文件变更**:
- `src/web/templates/recordings.html` - 添加播放器 UI
- `src/web/static/js/audio-player.js` - 播放器逻辑
- `src/web/static/css/audio-player.css` - 播放器样式

---

### 3. 语音转文字结果展示

**需求描述**: 显示每条录音的识别结果，包括原文、规范化文本、置信度

**实施步骤**:
1. 增强 API 返回识别详情
   - asr_text - 识别原文
   - content_normalized - 规范化文本
   - signal_type - 信号类型
   - confidence - 置信度
2. 前端展示
   - 在列表中显示识别文本摘要
   - 点击展开完整识别结果
   - 高亮显示关键词
   - 显示音频质量指标 (RMS, SNR)

**文件变更**:
- `src/api/recordings.py` - 返回识别详情
- `src/web/templates/recordings.html` - 显示识别结果
- `src/web/static/js/recordings.js` - 处理识别数据

---

### 4. 纠错规则管理

**需求描述**: 用户可以管理纠错规则，包括创建、编辑、删除、启用/禁用规则

**实施步骤**:
1. 增强 API 功能
   - 批量操作（批量启用/禁用）
   - 规则导入/导出
   - 规则测试功能
2. 前端管理界面
   - 规则列表（可排序、筛选）
   - 规则编辑器（支持正则表达式测试）
   - 规则分类管理

**文件变更**:
- `src/api/rules.py` - 增强规则 API
- `src/web/templates/rules.html` - 规则管理页面
- `src/web/static/js/rules.js` - 规则管理逻辑

---

## 实施优先级

| 优先级 | 功能 | 预计工作量 | 依赖 |
|--------|------|------------|------|
| P0 (高) | 实时录音列表查看 | 2-3小时 | 无 |
| P1 (高) | 语音转文字结果展示 | 2-3小时 | P0 |
| P2 (中) | 在线音频播放 | 3-4小时 | P0 |
| P3 (中) | 纠错规则管理增强 | 2-3小时 | 无 |

**总预计工作量**: 9-13 小时

---

## 技术实施细节

### 后端 (FastAPI)

#### 1. 录音列表 API 增强

```python
@router.get("/recordings")
async def get_recordings(
    page: int = 1,
    page_size: int = 20,
    date_from: Optional[str] = None,  # 新增
    date_to: Optional[str] = None,    # 新增
    signal_type: Optional[str] = None, # 新增
    sort_by: str = "timestamp",        # 新增
    sort_order: str = "desc",          # 新增
    ...
):
```

#### 2. 录音统计 API

```python
@router.get("/recordings/statistics")
async def get_recording_statistics(
    date: Optional[str] = None,
    channel_id: Optional[int] = None,
):
```

### 前端 (HTML + JS + Tailwind CSS)

#### 1. 录音列表页面结构

```html
<!-- 统计卡片 -->
<div class="stats-grid">
  <div class="stat-card">今日录音数</div>
  <div class="stat-card">今日总时长</div>
  <div class="stat-card">用户数</div>
</div>

<!-- 筛选面板 -->
<div class="filter-panel">
  <input type="date" id="dateFrom">
  <input type="date" id="dateTo">
  <select id="signalType">
    <option value="">全部信号类型</option>
    <option value="CQ">CQ 呼叫</option>
    <option value="QSO">QSO 通话</option>
  </select>
</div>

<!-- 录音列表 -->
<div class="recordings-table">
  <table>
    <thead>
      <tr>
        <th>时间</th>
        <th>用户</th>
        <th>时长</th>
        <th>识别结果</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody id="recordingsBody">
      <!-- 动态加载 -->
    </tbody>
  </table>
</div>
```

#### 2. 音频播放器组件

```javascript
class AudioPlayer {
  constructor() {
    this.audio = new Audio();
    this.currentTrack = null;
    this.playlist = [];
  }

  play(url) {
    this.audio.src = url;
    this.audio.play();
  }

  pause() {
    this.audio.pause();
  }

  setSpeed(speed) {
    this.audio.playbackRate = speed;
  }
}
```

---

## 测试计划

### 功能测试
1. 录音列表加载和筛选
2. 分页功能
3. 音频播放控制
4. 识别结果展示
5. 纠错规则 CRUD 操作

### 性能测试
1. 大量录音（1000+）的列表加载性能
2. 音频播放流畅度
3. 实时筛选响应速度

### 兼容性测试
1. Chrome/Edge/Firefox
2. 移动端浏览器

---

## 部署注意事项

1. **静态文件缓存**: 音频文件需要合理的缓存策略
2. **跨域问题**: 如果使用分离部署，需要配置 CORS
3. **大文件处理**: 考虑音频文件的范围请求支持
4. **数据库索引**: 确保 recordings 表的查询字段有索引

---

## 后续优化方向

1. **实时更新**: 使用 WebSocket 推送新录音通知
2. **音频转码**: 提供多种格式/码率的音频
3. **语音高亮**: 在波形上标注语音段
4. **批量操作**: 批量下载、批量识别
5. **数据导出**: 导出录音列表为 CSV/Excel
