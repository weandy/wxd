@echo off
echo ========================================
echo  BSHT Bot - 多频道监听机器人
echo ========================================
echo.

REM 检查配置文件
if not exist channels.json (
    echo [错误] 未找到 channels.json 配置文件
    pause
    exit /b 1
)

echo [配置] 从 channels.json 加载频道配置...
echo.
echo 启动多频道监听机器人...
echo.
echo 功能说明:
echo   - 自动连接配置的频道
echo   - 录制所有通联音频
echo   - 语音识别并推送
echo   - 按 Ctrl+C 停止
echo.
echo ========================================
echo.

python multi_channel_bot.py --config channels.json

pause
