"""
BSHT Bot Web 服务器
FastAPI + SQLite + Tailwind CSS
"""
import os
import sys
from pathlib import Path

# 强制无缓冲输出
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

# 配置
SECRET_KEY = os.getenv("WEB_SECRET_KEY", "bsht-bot-secret-key-change-in-production")
SESSION_COOKIE_NAME = "bsht_session"

# 创建 FastAPI 应用
app = FastAPI(
    title="BSHT Bot Web 管理平台",
    description="BSHT Bot Web 管理接口",
    version="1.0.0"
)

# Session 中间件
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=86400  # 24 小时
)

# 模板配置
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "src" / "web" / "templates"))

# 确保必要的目录存在
(BASE_DIR / "recordings").mkdir(exist_ok=True)
(BASE_DIR / "data" / "audio_library").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "audio_uploads").mkdir(exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "src" / "web" / "static")), name="static")
app.mount("/recordings", StaticFiles(directory=str(BASE_DIR / "recordings")), name="recordings")
app.mount("/audio_library", StaticFiles(directory=str(BASE_DIR / "data" / "audio_library")), name="audio_library")
app.mount("/audio_uploads", StaticFiles(directory=str(BASE_DIR / "audio_uploads")), name="audio_uploads")


# ====================
# 依赖项
# ====================

def get_current_user(request: Request):
    """获取当前登录用户"""
    user = request.session.get("user")
    if not user:
        return None
    return user


def require_auth(request: Request):
    """需要认证"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录"
        )
    return user


def require_admin(request: Request):
    """需要管理员权限"""
    user = require_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return user


# ====================
# 基础路由
# ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    user = get_current_user(request)
    if user:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "current_user": user}
        )
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """仪表板页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "current_user": user}
    )


@app.get("/recordings", response_class=HTMLResponse)
async def recordings_page(request: Request):
    """录音列表页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "recordings.html",
        {"request": request, "current_user": user}
    )


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    """纠错规则管理页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "rules.html",
        {"request": request, "current_user": user}
    )


@app.get("/push", response_class=HTMLResponse)
async def push_page(request: Request):
    """推送服务管理页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "push.html",
        {"request": request, "current_user": user}
    )


@app.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    """广播任务管理页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "broadcast.html",
        {"request": request, "current_user": user}
    )


@app.get("/audio-library", response_class=HTMLResponse)
async def audio_library_page(request: Request):
    """音频库管理页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "audio_library.html",
        {"request": request, "current_user": user}
    )


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request):
    """机器人监控页面"""
    user = require_auth(request)
    return templates.TemplateResponse(
        "monitor.html",
        {"request": request, "current_user": user}
    )


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "bsht-bot-web"}


# ====================
# API 路由
# ====================

# 认证 API
from src.api import auth
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# 录音 API
from src.api import recordings
app.include_router(recordings.router, prefix="/api", tags=["recordings"])

# 仪表盘 API
from src.api import dashboard
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])

# 规则管理 API
from src.api import rules
app.include_router(rules.router, prefix="/api", tags=["rules"])

# 推送服务 API
from src.api import push
app.include_router(push.router, prefix="/api", tags=["push"])

# 广播任务 API
from src.api import broadcast
app.include_router(broadcast.router, prefix="/api", tags=["broadcast"])

# 音频库 API
from src.api import audio_library
app.include_router(audio_library.router, prefix="/api", tags=["audio_library"])

# 音频上传 API
from src.api import audio_upload
app.include_router(audio_upload.router, prefix="/api", tags=["audio_upload"])

# 监控 API
from src.api import monitor
app.include_router(monitor.router, prefix="/api", tags=["monitor"])


# ====================
# 开发服务器入口
# ====================

if __name__ == "__main__":
    print("BSHT Bot Web 服务器启动...")
    print(f"访问地址: http://localhost:8000")
    print(f"工作目录: {BASE_DIR}")

    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式自动重载
        log_level="info"
    )
