# BSHT Bot Web 平台 - 生产环境部署指南

## 目录

1. [系统要求](#系统要求)
2. [环境准备](#环境准备)
3. [应用部署](#应用部署)
4. [反向代理配置](#反向代理配置)
5. [进程管理](#进程管理)
6. [监控与日志](#监控与日志)
7. [安全加固](#安全加固)
8. [备份策略](#备份策略)

---

## 系统要求

### 最低配置
- **CPU**: 1 核
- **内存**: 1GB RAM
- **磁盘**: 5GB 可用空间
- **操作系统**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+

### 推荐配置
- **CPU**: 2+ 核
- **内存**: 2GB+ RAM
- **磁盘**: 20GB+ SSD
- **操作系统**: Ubuntu 22.04 LTS

### 软件要求
- **Python**: 3.8 或更高版本
- **pip**: 最新版本
- **git**: 最新版本

---

## 环境准备

### 1. 安装系统依赖

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git nginx sqlite3
```

**CentOS/RHEL**:
```bash
sudo yum install -y python3 python3-pip git nginx sqlite3
```

### 2. 创建应用用户

```bash
# 创建专用用户
sudo useradd -m -s /bin/bash bsht-bot
sudo passwd bsht-bot

# 创建应用目录
sudo mkdir -p /opt/bsht-bot
sudo chown bsht-bot:bsht-bot /opt/bsht-bot
```

### 3. 切换到应用用户

```bash
sudo su - bsht-bot
cd /opt/bsht-bot
```

### 4. 克隆代码仓库

```bash
git clone <your-repository-url> .
# 或上传代码文件
```

---

## 应用部署

### 方案 1: 直接部署

#### 1. 创建 Python 虚拟环境

```bash
cd /opt/bsht-bot
python3 -m venv venv
source venv/bin/activate
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
pip install gunicorn
```

#### 3. 配置环境变量

```bash
cp .env.example .env
nano .env  # 编辑配置
```

**必须配置的环境变量**:
```bash
# 安全配置
WEB_SECRET_KEY=<your-secret-key-here>

# BSHT Bot 配置
BSHT_USERNAME=<your-username>
BSHT_PASSWORD=<your-password>
BSHT_CHANNEL_ID=<your-channel-id>

# AI 识别配置（可选）
SILICONFLOW_API_KEY=<your-api-key>
```

#### 4. 初始化数据库

```bash
python -c "from src.database import Database; Database().init_db()"
```

#### 5. 创建必要目录

```bash
mkdir -p data recordings log
chmod 755 data recordings log
```

#### 6. 测试启动

```bash
python web_server.py
# 访问 http://localhost:8000 测试
# Ctrl+C 停止
```

### 方案 2: Docker 部署

#### 1. 创建 Dockerfile

```dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p data recordings log

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# 启动应用
CMD ["gunicorn", "web_server:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0", "8000", \
     "--timeout", "120", \
     "--access-logfile", "/app/log/access.log", \
     "--error-logfile", "/app/log/error.log"]
```

#### 2. 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  web:
    build: .
    container_name: bsht-bot-web
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - WEB_SECRET_KEY=${WEB_SECRET_KEY}
      - BSHT_USERNAME=${BSHT_USERNAME}
      - BSHT_PASSWORD=${BSHT_PASSWORD}
      - BSHT_CHANNEL_ID=${BSHT_CHANNEL_ID}
      - SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY}
    volumes:
      - ./data:/app/data
      - ./recordings:/app/recordings
      - ./log:/app/log
    networks:
      - bsht-network

  nginx:
    image: nginx:alpine
    container_name: bsht-bot-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - web
    networks:
      - bsht-network

networks:
  bsht-network:
    driver: bridge
```

#### 3. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f web

# 停止服务
docker-compose down
```

---

## 反向代理配置

### Nginx 配置

#### 1. HTTP 配置

`/etc/nginx/sites-available/bsht-bot-http.conf`:

```nginx
upstream bsht_bot_backend {
    server 127.0.0.1:8000;
    # 如有多个 worker，可以添加多个 server
    # server 127.0.0.1:8001;
    # server 127.0.0.1:8002;
}

server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # 强制 HTTPS (可选)
    # return 301 https://$server_name$request_uri;

    # 日志
    access_log /var/log/nginx/bsht-bot-access.log;
    error_log /var/log/nginx/bsht-bot-error.log;

    # 静态文件
    location /static/ {
        alias /opt/bsht-bot/src/web/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 录音文件
    location /recordings/ {
        alias /opt/bsht-bot/recordings/;
        expires 7d;
    }

    # 音频库文件
    location /audio_library/ {
        alias /opt/bsht-bot/data/audio_library/;
        expires 30d;
    }

    # API 和其他请求
    location / {
        proxy_pass http://bsht_bot_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 上传文件大小限制
    client_max_body_size 100M;
}
```

#### 2. HTTPS 配置

`/etc/nginx/sites-available/bsht-bot-https.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/privkey.pem;

    # SSL 优化
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_protocols TLSv1.2 TLSv1.3;

    # 其他配置同 HTTP
    # ...

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}

# HTTP to HTTPS 重定向
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

#### 3. 启用配置

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/bsht-bot-http.conf /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/bsht-bot-https.conf /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

---

## 进程管理

### Systemd 服务

#### 1. 创建服务文件

`/etc/systemd/system/bsht-bot.service`:

```ini
[Unit]
Description=BSHT Bot Web Service
Documentation=https://github.com/your-repo/wiki
After=network.target

[Service]
Type=notify
User=bsht-bot
Group=bsht-bot
WorkingDirectory=/opt/bsht-bot
Environment="PATH=/opt/bsht-bot/venv/bin"
EnvironmentFile=/opt/bsht-bot/.env

ExecStart=/opt/bsht-bot/venv/bin/gunicorn web_server:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile /opt/bsht-bot/log/access.log \
    --error-logfile /opt/bsht-bot/log/error.log \
    --log-level info

ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=always
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

#### 2. 启动和管理服务

```bash
# 重新加载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start bsht-bot

# 设置开机自启
sudo systemctl enable bsht-bot

# 查看服务状态
sudo systemctl status bsht-bot

# 查看日志
sudo journalctl -u bsht-bot -f

# 重启服务
sudo systemctl restart bsht-bot

# 停止服务
sudo systemctl stop bsht-bot
```

---

## 监控与日志

### 日志管理

#### 1. 日志轮转

创建 `/etc/logrotate.d/bsht-bot`:

```
/opt/bsht-bot/log/*.log
{
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 bsht-bot bsht-bot-bot
    sharedscripts
    postrotate
    systemctl reload bsht-bot > /dev/null 2>&1 || true
}
```

#### 2. 日志查看

```bash
# 应用日志
tail -f /opt/bsht-bot/log/error.log

# 系统服务日志
sudo journalctl -u bsht-bot -f

# Nginx 访问日志
sudo tail -f /var/log/nginx/bsht-bot-access.log
```

### 性能监控

#### 1. 使用 Prometheus + Grafana

**安装 Node Exporter**:
```bash
wget https://github.com/prometheus/node_exporter/releases/download/v1.6.0/node_exporter-1.6.0.linux-amd64.tar.gz
tar xvfz node_exporter-1.6.0.linux-amd64.tar.gz
cd node_exporter-1.6.0
./node_exporter --web.listen-address=:9100 &
```

#### 2. 监控进程

```bash
# 添加到 crontab
crontab -e

# 每5分钟检查进程状态
*/5 * * * * /opt/bsht-bot/scripts/check_process.sh
```

---

## 安全加固

### 1. 防火墙配置

```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable

# firewalld (CentOS)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 2. Fail2Ban 防护

```bash
sudo apt install fail2ban

# 配置 /etc/fail2ban/jail.local
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true
```

### 3. 定期更新

```bash
# 添加到 crontab
0 2 * * * /opt/bsht-bot/scripts/update.sh
```

---

## 备份策略

### 1. 数据库备份

**自动备份脚本** `/opt/bsht-bot/scripts/backup_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/bsht-bot/backups"
DB_PATH="/opt/bsht-bot/data/records.db"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/records_$DATE.db"

mkdir -p $BACKUP_DIR

# 备份数据库
cp $DB_PATH $BACKUP_FILE

# 压缩备份
gzip $BACKUP_FILE

# 删除 30 天前的备份
find $BACKUP_DIR -name "*.db.gz" -mtime +30 -delete

echo "Backup completed: records_$DATE.db.gz"
```

**添加到 crontab**:
```bash
# 每天凌晨 2 点备份
0 2 * * * /opt/bsht-bot/scripts/backup_db.sh
```

### 2. 录音文件备份

```bash
# 使用 rsync 同步到备份服务器
rsync -avz /opt/bsht-bot/recordings/ user@backup-server:/backup/recordings/
```

### 3. 配置备份

```bash
# 备份环境配置和 Nginx 配置
tar czf config_backup_$(date +%Y%m%d).tar.gz \
    .env \
    nginx/ \
    > /opt/bsht-bot/backups/config_backup.tar.gz
```

---

## 故障排查

### 常见问题

#### 1. 服务启动失败

```bash
# 检查端口占用
sudo netstat -tulpn | grep :8000

# 检查日志
sudo journalctl -u bsht-bot -n 50

# 手动启动测试
cd /opt/bsht-bot
source venv/bin/activate
python web_server.py
```

#### 2. 数据库锁定

```bash
# 检查锁文件
lsof data/records.db

# 如果有进程占用
sudo killall -9 python
```

#### 3. 内存不足

```bash
# 检查内存使用
free -h

# 增加 swap
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 更新部署

### 滚动更新流程

1. **备份当前版本**
```bash
/opt/bsht-bot/scripts/backup_db.sh
```

2. **拉取最新代码**
```bash
git pull origin main
```

3. **更新依赖**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

4. **数据库迁移（如需要）**
```bash
python scripts/migrate_db.py
```

5. **重启服务**
```bash
sudo systemctl restart bsht-bot
```

---

## 性能优化

### 1. Gunicorn 优化

```ini
[Unit]
Description=BSHT Bot Web Service (Optimized)
...
[Service]
ExecStart=/opt/bsht-bot/venv/bin/gunicorn web_server:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --threads 2 \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --timeout 120 \
    --keepalive 5 \
    --preload \
    --access-logfile /opt/bsht-bot/log/access.log \
    --error-logfile /opt/bsht-bot/log/error.log
```

### 2. 数据库优化

```python
# 在 analyze_performance.py 中创建的索引
CREATE INDEX idx_recordings_timestamp ON recordings(timestamp);
CREATE INDEX idx_recordings_user_id ON recordings(user_id);
CREATE INDEX idx_recordings_channel_id ON recordings(channel_id);
CREATE INDEX idx_recordings_recognized ON recordings(recognized);
```

---

## 监控告警

### 邮件告警配置

```bash
# 安装 mailx
sudo apt install mailutils

# 配置发邮件
echo "test email" | mailx -s "Test Email" admin@example.com
```

### 服务监控脚本

`/opt/bsht-bot/scripts/check_service.sh`:

```bash
#!/bin/bash
# 检查服务状态
curl -f http://localhost:8000/health || {
    echo "Service is down, restarting..." | mailx -s "BSHT Bot Alert" admin@example.com
    sudo systemctl restart bsht-bot
}
```

---

## 完整部署检查清单

- [ ] 系统依赖已安装
- [ ] 应用用户已创建
- [ ] 代码已部署
- [ ] Python 虚拟环境已创建
- [ ] 依赖已安装
- [ ] 环境变量已配置
- [ ] 数据库已初始化
- [ ] 服务可正常启动
- [ ] Nginx 反向代理已配置
- [ ] Systemd 服务已配置
- [ ] 日志轮转已配置
- [ ] 防火墙规则已配置
- [ ] 备份脚本已配置
- [ ] 监控告警已配置
- [ ] HTTPS 证书已配置

---

**最后更新**: 2026-03-04
**维护者**: BSHT Bot Team
