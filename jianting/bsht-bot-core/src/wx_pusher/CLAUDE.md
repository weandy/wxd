[根目录](../CLAUDE.md) > [src/](../) > **wx_pusher.py**

---

# 微信推送模块

## 模块职责

基于 go-wxpush 服务的微信消息推送模块，支持关键词触发推送和多目标用户管理。

## 入口与启动

```python
from wx_pusher import WxPusher, PushTarget

# 创建推送目标
targets = [
    PushTarget(
        userid="user_openid_1",
        name="用户1",
        keywords=["CQ", "紧急"]
    ),
    PushTarget(
        userid="user_openid_2",
        name="用户2",
        keywords=[]  # 接收所有消息
    )
]

# 创建推送器
pusher = WxPusher(
    url="http://your-wxpush-server:8080/wxsend",
    token="your-token",
    targets=targets
)

# 发送推送
pusher.send(
    title="BSHT 识别结果",
    content="检测到 CQ 呼叫: 这里是内容"
)
```

## 对外接口

### WxPusher
- `send(title, content, userid=None)` - 发送推送消息

### PushTarget
```python
@dataclass
class PushTarget:
    userid: str           # 微信 OpenID
    name: str             # 备注名称
    keywords: List[str]   # 关键词列表，为空表示接收所有
```

## 关键依赖

- `requests` - HTTP 请求库

## 配置项

- **URL**: go-wxpush 服务地址
- **Token**: 认证 Token
- **Targets**: 推送目标列表，每个目标可配置关键词过滤

## 工作流程

1. 识别结果生成
2. 根据关键词匹配目标用户
3. 发送 POST 请求到 go-wxpush 服务
4. 服务推送到对应微信用户

## 常见问题

- **go-wxpush 服务**: 需要部署 go-wxpush 服务端
- **关键词匹配**: 空关键词列表表示接收所有消息
- **错误处理**: 多种成功标志判断 (errcode=0, code=0, msg包含ok/success)

## 相关文件

- `src/recognizer.py` - 调用本模块进行推送
- `src/main.py` - 配置和使用本模块

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
