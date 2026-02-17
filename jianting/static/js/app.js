class BSHTWebApp {
    constructor() {
        this.socket = null;
        this.botState = {
            state: 'stopped',
            connected_channel: null,
            is_transmitting: false,
            current_speakers: []
        };
        this.pttActive = false;
        this.pttButton = null;
        this.recordings = [];

        this.init();
    }

    init() {
        this.initWebSocket();
        this.bindEvents();
        this.loadChannels();
        this.loadRecordings();
        this.updateUI();
    }

    initWebSocket() {
        this.socket = io('/bot');

        this.socket.on('connect', () => {
            this.showNotification('已连接到服务器', 'success');
            this.updateConnectionStatus(true);
        });

        this.socket.on('disconnect', () => {
            this.showNotification('与服务器断开连接', 'error');
            this.updateConnectionStatus(false);
        });

        this.socket.on('bot_status_changed', (data) => {
            this.botState = data;
            this.updateUI();
        });

        this.socket.on('speaker_started', (data) => {
            this.updateSpeakersUI();
        });

        this.socket.on('speaker_stopped', (data) => {
            this.updateSpeakersUI();
        });

        this.socket.on('transmit_started', () => {
            this.setPTTState(true);
        });

        this.socket.on('transmit_stopped', () => {
            this.setPTTState(false);
        });

        this.socket.on('audio_recorded', (data) => {
            this.recordings.unshift(data);
            this.renderRecordings();
            this.showNotification(`新录音: ${data.speaker_name}`, 'info');
        });
    }

    async apiCall(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options
            });
            return await response.json();
        } catch (error) {
            this.showNotification(`请求失败: ${error.message}`, 'error');
            throw error;
        }
    }

    async startBot() {
        await this.apiCall('/api/bot/start', { method: 'POST' });
        this.showNotification('Bot 启动中...', 'info');
    }

    async stopBot() {
        await this.apiCall('/api/bot/stop', { method: 'POST' });
        this.showNotification('Bot 正在停止...', 'info');
    }

    async loadChannels() {
        const channels = await this.apiCall('/api/channels');

        const select = document.getElementById('channel-select');
        const filterSelect = document.getElementById('filter-channel');

        select.innerHTML = '<option value="">选择频道...</option>';
        filterSelect.innerHTML = '<option value="all">所有频道</option>';

        channels.forEach(ch => {
            select.add(new Option(`${ch.name} (${ch.channel_id})`, ch.channel_id));
            if (ch.configured) {
                filterSelect.add(new Option(`${ch.name}`, ch.channel_id));
            }
        });
    }

    async joinChannel() {
        const channelId = document.getElementById('channel-select').value;
        if (!channelId) {
            this.showNotification('请选择频道', 'warning');
            return;
        }
        await this.apiCall(`/api/channels/${channelId}/join`, { method: 'POST' });
        this.showNotification('正在加入频道...', 'info');
    }

    async leaveChannel() {
        await this.apiCall(`/api/channels/leave`, { method: 'POST' });
        this.showNotification('正在离开频道...', 'info');
    }

    async startPTT() {
        try {
            await this.apiCall('/api/ptt/start', { method: 'POST' });
        } catch (e) {
            this.setPTTState(false);
        }
    }

    async stopPTT() {
        try {
            await this.apiCall('/api/ptt/stop', { method: 'POST' });
        } catch (e) {
            this.setPTTState(false);
        }
    }

    setPTTState(active) {
        this.pttActive = active;
        if (this.pttButton) {
            if (active) {
                this.pttButton.classList.add('active');
                this.pttButton.querySelector('.ptt-text').textContent = '正在发射...';
            } else {
                this.pttButton.classList.remove('active');
                this.pttButton.querySelector('.ptt-text').textContent = '按住说话';
            }
        }
    }

    async loadRecordings() {
        const channelId = document.getElementById('filter-channel').value;
        const url = channelId && channelId !== 'all'
            ? `/api/recordings?channel_id=${channelId}&limit=50`
            : `/api/recordings?limit=50`;
        this.recordings = await this.apiCall(url);
        this.renderRecordings();
    }

    renderRecordings() {
        const tbody = document.getElementById('recordings-list');

        if (this.recordings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">暂无录音记录</td></tr>';
            return;
        }

        tbody.innerHTML = this.recordings.map(rec => `
            <tr>
                <td>${this.formatDateTime(rec.start_time)}</td>
                <td>${this.escapeHtml(rec.speaker_name)}</td>
                <td>${this.formatDuration(rec.duration_sec)}</td>
                <td>${this.formatLossRate(rec.loss_rate)}</td>
                <td>
                    <button class="btn btn-outline" onclick="app.playRecording(${rec.id})" style="padding:0.25rem 0.5rem;font-size:0.875rem;">播放</button>
                    <button class="btn btn-outline" onclick="app.downloadRecording(${rec.id})" style="padding:0.25rem 0.5rem;font-size:0.875rem;">下载</button>
                    <button class="btn btn-danger" onclick="app.deleteRecording(${rec.id})" style="padding:0.25rem 0.5rem;font-size:0.875rem;">删除</button>
                </td>
            </tr>
        `).join('');
    }

    async playRecording(id) {
        const rec = await this.apiCall(`/api/recordings/${id}`);
        const modal = document.getElementById('audio-modal');
        const player = document.getElementById('audio-player');
        const title = document.getElementById('audio-modal-title');

        title.textContent = `${rec.speaker_name} - ${this.formatDateTime(rec.start_time)}`;
        player.src = `/api/recordings/${id}/download`;
        modal.classList.add('active');
    }

    downloadRecording(id) {
        window.open(`/api/recordings/${id}/download`, '_blank');
    }

    async deleteRecording(id) {
        if (!confirm('确定要删除这条录音吗？')) return;
        await this.apiCall(`/api/recordings/${id}`, { method: 'DELETE' });
        this.recordings = this.recordings.filter(r => r.id !== id);
        this.renderRecordings();
        this.showNotification('录音已删除', 'success');
    }

    bindEvents() {
        document.getElementById('btn-start-bot').addEventListener('click', () => this.startBot());
        document.getElementById('btn-stop-bot').addEventListener('click', () => this.stopBot());
        document.getElementById('btn-join-channel').addEventListener('click', () => this.joinChannel());
        document.getElementById('btn-leave-channel').addEventListener('click', () => this.leaveChannel());

        this.pttButton = document.getElementById('btn-ptt');

        this.pttButton.addEventListener('mousedown', (e) => {
            e.preventDefault();
            this.startPTT();
        });

        document.addEventListener('mouseup', () => {
            if (this.pttActive) this.stopPTT();
        });

        this.pttButton.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.startPTT();
        });

        this.pttButton.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.stopPTT();
        });

        document.getElementById('filter-channel').addEventListener('change', () => this.loadRecordings());
        document.getElementById('btn-load-more').addEventListener('click', () => this.loadRecordings());

        document.querySelector('.modal-close').addEventListener('click', () => {
            document.getElementById('audio-modal').classList.remove('active');
        });

        document.getElementById('audio-modal').addEventListener('click', (e) => {
            if (e.target.id === 'audio-modal') {
                document.getElementById('audio-modal').classList.remove('active');
            }
        });
    }

    updateUI() {
        const stateBadge = document.getElementById('bot-state');
        stateBadge.className = 'status-badge';
        stateBadge.classList.add(this.botState.state);

        const stateText = {
            'stopped': '已停止',
            'starting': '启动中',
            'running': '运行中',
            'stopping': '停止中',
            'error': '错误'
        };
        stateBadge.textContent = stateText[this.botState.state] || this.botState.state;

        const channelDisplay = document.getElementById('current-channel');
        channelDisplay.textContent = this.botState.connected_channel
            ? `频道 ${this.botState.connected_channel}`
            : '未连接';

        this.updateSpeakersUI();

        document.getElementById('btn-start-bot').disabled = this.botState.state !== 'stopped';
        document.getElementById('btn-stop-bot').disabled = this.botState.state === 'stopped';
    }

    updateSpeakersUI() {
        const speakersDisplay = document.getElementById('current-speakers');
        if (this.botState.current_speakers && this.botState.current_speakers.length > 0) {
            speakersDisplay.textContent = `${this.botState.current_speakers.length} 人正在说话`;
        } else {
            speakersDisplay.textContent = '-';
        }
    }

    updateConnectionStatus(connected) {
        const statusBadge = document.getElementById('connection-status');
        statusBadge.className = 'status-badge';
        statusBadge.classList.add(connected ? 'online' : 'offline');
        statusBadge.textContent = connected ? '在线' : '离线';
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;

        const colors = {
            'success': '#dcfce7',
            'error': '#fee2e2',
            'warning': '#fef3c7',
            'info': '#dbeafe'
        };
        toast.style.background = colors[type] || colors.info;

        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    formatDateTime(isoString) {
        if (!isoString) return '-';
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    formatDuration(seconds) {
        if (seconds < 60) return `${seconds.toFixed(1)}秒`;
        const minutes = Math.floor(seconds / 60);
        const secs = (seconds % 60).toFixed(1);
        return `${minutes}分${secs}秒`;
    }

    formatLossRate(rate) {
        if (rate === 0) return '0%';
        return `${(rate * 100).toFixed(2)}%`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

const app = new BSHTWebApp();
