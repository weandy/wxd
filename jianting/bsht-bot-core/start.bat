@echo off
echo ========================================
echo  BSHT Bot Web 平台 - 启动脚本
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo [1/3] 检查依赖...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [信息] 正在安装依赖...
    pip install -r requirements.txt
)

echo [2/3] 初始化数据库...
python -c "from src.database import Database; Database().init_db()" 2>nul

echo [3/3] 启动 Web 服务器...
echo.
echo ========================================
echo  服务地址: http://localhost:8000
echo  登录账号: admin / admin123
echo ========================================
echo.
echo 按 Ctrl+C 停止服务器
echo.

python web_server.py

pause
