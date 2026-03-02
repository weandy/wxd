"""
认证 API - 登录、登出、获取当前用户
"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, status, Depends
from pydantic import BaseModel

from src.database import Database
from src.services.auth_service import auth_service


router = APIRouter()


# ===== 请求模型 =====

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    code: int
    message: str
    data: Optional[dict] = None


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    code: int
    message: str
    data: Optional[dict] = None


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


def get_current_user(request: Request) -> dict:
    """获取当前登录用户"""
    # 从 Session 获取用户信息
    user = request.session.get("user")

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录"
        )

    return user


# ===== API 端点 =====

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Database = Depends(get_db)
):
    """
    用户登录

    Args:
        request: FastAPI Request
        login_data: 登录数据
        db: 数据库实例

    Returns:
        登录结果
    """
    # 验证用户凭据
    user_info = auth_service.authenticate_user(
        db,
        login_data.username,
        login_data.password
    )

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 创建会话
    request.session["user"] = user_info
    request.session["user_id"] = user_info["id"]

    return LoginResponse(
        code=0,
        message="登录成功",
        data={
            "id": user_info["id"],
            "username": user_info["username"],
            "nickname": user_info["nickname"],
            "role": user_info["role"]
        }
    )


@router.post("/logout")
async def logout(request: Request):
    """
    用户登出

    Args:
        request: FastAPI Request

    Returns:
        登出结果
    """
    # 清除会话
    request.session.clear()

    return {
        "code": 0,
        "message": "登出成功"
    }


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    """
    获取当前用户信息

    Args:
        current_user: 当前用户（从依赖项获取）

    Returns:
        用户信息
    """
    return UserInfoResponse(
        code=0,
        message="success",
        data=current_user
    )


# ===== 健康检查 =====

@router.get("/health")
async def health_check():
    """认证服务健康检查"""
    return {
        "status": "ok",
        "service": "auth"
    }
