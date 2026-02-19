# BSHT 部署指南

本指南介绍如何在 Windows 和 Linux (Ubuntu/Debian) 服务器上部署 BSHT 机器人。

## 目录
1. [前置要求](#前置要求)
2. [环境准备](#环境准备)
3. [Windows 部署](#windows-部署)
4. [Linux 部署](#linux-部署)
5. [常见问题](#常见问题)

---

## 前置要求

- Python 3.8 或更高版本
- 稳定的网络连接 (需连接 `rpc.benshikj.com` 和语音服务器 IP)

## 环境准备

### 1. 依赖库
项目依赖以下 Python 库:
- `httpx[http2]`
- `msgpack`
- `numpy`
- `pyaudio`

### 2. 系统库 (Linux 必须)
- `portaudio` (用于 PyAudio)
- `libopus` (用于 Opus 编解码)

---

## Windows 部署

1. **安装 Python**: 确保安装了 Python 3.8+ 并添加到 PATH。
2. **安装依赖**:
   打开 PowerShell 或 CMD，在项目目录下运行:
   ```powershell
   pip install -r requirements.txt
   ```
   *(注意: Windows 下安装 pyaudio 可能会报错，如果报错请下载对应版本的 .whl 文件手动安装，或者使用 `pip install pipwin` 然后 `pipwin install pyaudio`)*

3. **配置账号**:
   修改 `bot_server.py` 文件中的配置部分:
   ```python
   # 配置
   USERNAME = "your_username"
   PASSWORD = "your_password"
   CHANNEL_ID = 62793  # 目标频道ID
   ```

4. **运行**:
   可以直接运行脚本:
   ```powershell
   python bot_server.py
   ```

---

## Linux 部署 (Ubuntu/Debian)

推荐使用 Screen 或 Systemd 来后台运行。

### 1. 安装系统依赖
```bash
sudo apt-get update
sudo apt-get install python3-pip python3-venv portaudio19-dev libopus0 libopus-dev -y
```

### 2. 创建虚拟环境 (推荐)
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

### 4. 配置账号
使用 `nano` 或 `vim` 修改 `bot_server.py`:
```bash
nano bot_server.py
```
修改 `USERNAME`, `PASSWORD`, `CHANNEL_ID`。

### 5. 运行测试
```bash
python bot_server.py
```
如果看到 `[Opus] 已加载库: libopus.so.0` (或类似) 且登录成功，说明环境正常。

### 6. 后台运行 (Screen 方式)
```bash
# 安装 screen
sudo apt-get install screen -y

# 创建新会话
screen -S bsht

# 在会话中运行
python bot_server.py

# 按 Ctrl+A 然后按 D detach (后台运行)
```
要恢复查看: `screen -r bsht`

### 7. 后台运行 (Systemd 服务方式 - 推荐 24h)

创建服务文件:
```bash
sudo nano /etc/systemd/system/bsht.service
```

内容如下 (假设项目在 `/opt/bsht`):
```ini
[Unit]
Description=BSHT Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/bsht
ExecStart=/opt/bsht/venv/bin/python bot_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bsht
sudo systemctl start bsht
```

查看日志:
```bash
sudo journalctl -u bsht -f
```

---

## 常见问题

### Q: 报错 `OSError: libopus.so.0: cannot open shared object file`
A: Linux 上没装 libopus。运行 `sudo apt-get install libopus0`。如果是 CentOS，试 `yum install opus`。

### Q: error: command 'gcc' failed with exit status 1 (安装 PyAudio 时)
A: 缺少 portaudio 开发头文件。运行 `sudo apt-get install portaudio19-dev`。

### Q: 录音文件在哪里？
A: 在 `recordings/` 目录下，按日期分类。
