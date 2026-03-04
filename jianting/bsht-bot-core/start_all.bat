@echo off
setlocal enabledelayedexpansion

REM 检查参数
if "%1"=="--status" goto STATUS
if "%1"=="--stop" goto STOP
if "%1"=="--web-only" goto WEB_ONLY
if "%1"=="--bot-only" goto BOT_ONLY

REM 默认：同时启动 Web + Bot
goto START_ALL

:START_ALL
echo ========================================
echo  BSHT Bot - 一键启动 (Web + Bot)
echo ========================================
echo.
python start.py
goto END

:WEB_ONLY
echo ========================================
echo  BSHT Bot - 只启动 Web 服务
echo ========================================
echo.
python start.py --web-only
goto END

:BOT_ONLY
echo ========================================
echo  BSHT Bot - 只启动 Bot 服务
echo ========================================
echo.
python start.py --bot-only
goto END

:STATUS
echo ========================================
echo  BSHT Bot - 服务状态
echo ========================================
echo.
python start.py --status
goto END

:STOP
echo ========================================
echo  BSHT Bot - 停止所有服务
echo ========================================
echo.
python start.py --stop
goto END

:END
pause
