"""
API 模块 - FastAPI 路由
"""
from fastapi import APIRouter

# 创建 API 路由
api_router = APIRouter()

# 导入各个模块的路由（将在后续添加）
# from .auth import router as auth_router
# api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
