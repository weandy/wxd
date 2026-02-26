/**
 * Live 页面控制器
 *
 * 整合 AudioMonitor (监听) / AudioTransmitter (发射) / 频道状态 / 历史录音
 */
(function () {
    'use strict';

    // ==================== 状态 ====================
    let socket = null;
    let monitor = null;
    let transmitter = null;
    let audioUnlocked = false;
    let currentChannelId = null;  // 由频道选择器控制

    // 录音分页
    const PER_PAGE = 5;
    let currentPage = 1;
    let totalPages = 1;
    let totalRecordings = 0;

    // 音频播放
    let currentPlayingId = null;
    let globalAudioPlayer = new Audio();

    // 运行时间自动更新
    let uptimeSeconds = 0;
    let uptimeTimer = null;

    // ==================== DOM ====================
    const $ = (sel) => document.querySelector(sel);

    // ==================== 初始化 ====================
    function init() {
        const token = localStorage.getItem('token');
        if (!token) {
            window.location.href = '/login';
            return;
        }

        socket = io({ query: { token } });
        monitor = new AudioMonitor(socket);
        transmitter = new AudioTransmitter(socket, true);  // 启用 WebRTC 模式

        bindSocketEvents();
        bindUIEvents();

        loadBotStatus();
        loadRecordings();

        // 全局播放器事件
        globalAudioPlayer.addEventListener('ended', () => {
            resetPlayingState();
        });
        globalAudioPlayer.addEventListener('timeupdate', () => {
            updateProgressBar();
        });

        // 频道选择器事件
        const txSelect = document.getElementById('txChannelSelect');
        if (txSelect) {
            txSelect.addEventListener('change', function () {
                currentChannelId = this.value ? parseInt(this.value) : null;
            });
        }

        // 页面离开时释放麦克风
        window.addEventListener('beforeunload', () => {
            if (transmitter) transmitter.dispose();
        });
    }

    // ==================== SocketIO 事件 ====================
    function bindSocketEvents() {
        socket.on('auth_ok', (data) => {
            updateElement('#statusConnected', '已连接');
        });
        socket.on('bot:status', (data) => updateBotStatus(data));
        socket.on('bot:speaking', (data) => updateSpeaker(data));
        socket.on('bot:channel', (data) => updateChannel(data));

        // 新录音 → 重新加载列表（保证数据准确，包含正确的 ID 和识别结果）
        socket.on('bot:recording', (data) => {
            console.log('[Live] 收到 bot:recording 事件:', data);
            if (currentPage === 1) {
                // 延迟 2 秒加载（等待识别完成写入数据库）
                setTimeout(() => loadRecordings(), 2000);
            }
        });

        socket.on('ptt:ready', () => {
            updateElement('#pttStatus', '发射中...');
            $('#pttBtn')?.classList.add('active');
        });
        socket.on('ptt:stopped', () => {
            updateElement('#pttStatus', '就绪');
            $('#pttBtn')?.classList.remove('active');
        });
        socket.on('error', (data) => showToast(data.message, 'error'));
        socket.on('disconnect', () => updateElement('#statusConnected', '已断开'));
    }

    // ==================== UI 事件 ====================
    function bindUIEvents() {
        const overlay = $('#audioOverlay');
        if (overlay) {
            overlay.addEventListener('click', async () => {
                try {
                    await monitor.startListening();
                    audioUnlocked = true;
                    overlay.classList.add('hidden');
                    updateElement('#listenStatus', '🔊 正在监听');
                } catch (e) {
                    showToast('音频初始化失败: ' + e.message, 'error');
                }
            });
        }

        // PTT
        const pttBtn = $('#pttBtn');
        if (pttBtn) {
            pttBtn.addEventListener('mousedown', (e) => { e.preventDefault(); startPTT(); });
            pttBtn.addEventListener('mouseup', stopPTT);
            pttBtn.addEventListener('mouseleave', stopPTT);
            pttBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startPTT(); });
            pttBtn.addEventListener('touchend', stopPTT);
            pttBtn.addEventListener('touchcancel', stopPTT);
        }

        // 空格键 PTT
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && !e.repeat && !isInputFocused()) { e.preventDefault(); startPTT(); }
        });
        document.addEventListener('keyup', (e) => {
            if (e.code === 'Space' && !isInputFocused()) { e.preventDefault(); stopPTT(); }
        });

        // 分页按钮
        const prevBtn = $('#prevPageBtn');
        const nextBtn = $('#nextPageBtn');
        if (prevBtn) prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadRecordings(); } });
        if (nextBtn) nextBtn.addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; loadRecordings(); } });
    }

    function isInputFocused() {
        const t = document.activeElement?.tagName;
        return t === 'INPUT' || t === 'TEXTAREA';
    }

    // ==================== PTT ====================
    async function startPTT() {
        if (transmitter.isTransmitting) return;
        if (!audioUnlocked) { showToast('请先点击页面解锁音频', 'warning'); return; }
        if (!currentChannelId) { showToast('频道未就绪，请稍候', 'warning'); return; }
        try {
            // 发射时静音监听, 防止回声
            if (monitor && monitor.playerNode) {
                monitor.playerNode.disconnect();
            }
            await transmitter.startTransmit(currentChannelId);
        } catch (e) { showToast('发射失败: ' + e.message, 'error'); }
    }
    function stopPTT() {
        if (!transmitter.isTransmitting) return;
        transmitter.stopTransmit();
        // 恢复监听播放
        if (monitor && monitor.playerNode && monitor.audioCtx) {
            try { monitor.playerNode.connect(monitor.audioCtx.destination); } catch (e) { }
        }
    }

    // ==================== Bot 状态 ====================
    function loadBotStatus() {
        fetch('/api/bot/status').then(r => r.json()).then(data => updateBotStatus(data)).catch(() => { });
    }

    function updateBotStatus(data) {
        updateElement('#botRunning', data.running ? '✅ 运行中' : '❌ 未运行');

        // 多频道状态显示
        const channels = data.channels || [];
        if (channels.length > 0) {
            const names = channels.map(ch => ch.channel_name || `CH:${ch.channel_id}`).join(', ');
            updateElement('#channelName', `${channels.length} 个: ${names}`);

            // 填充频道选择器
            const txSelect = document.getElementById('txChannelSelect');
            if (txSelect) {
                const oldVal = txSelect.value;
                txSelect.innerHTML = channels.map(ch =>
                    `<option value="${ch.channel_id}" style="background:#1e2330;color:#e4e6eb;">${ch.channel_name || '频道' + ch.channel_id} (ID:${ch.channel_id})</option>`
                ).join('');
                // 恢复选择
                if (oldVal && [...txSelect.options].some(o => o.value === oldVal)) {
                    txSelect.value = oldVal;
                }
                currentChannelId = parseInt(txSelect.value) || null;
            }
        } else if (data.channel_id) {
            // 兼容旧格式
            updateElement('#channelName', data.channel_name || '-');
            currentChannelId = data.channel_id;
            const txSelect = document.getElementById('txChannelSelect');
            if (txSelect) {
                txSelect.innerHTML = `<option value="${data.channel_id}" style="background:#1e2330;color:#e4e6eb;">${data.channel_name || '频道' + data.channel_id}</option>`;
            }
        } else {
            updateElement('#channelName', '-');
        }

        // 运行时间
        if (data.uptime) {
            uptimeSeconds = parseUptimeToSeconds(data.uptime);
            updateElement('#uptime', formatUptime(uptimeSeconds));
            startUptimeTimer();
        }
    }

    function startUptimeTimer() {
        if (uptimeTimer) clearInterval(uptimeTimer);
        uptimeTimer = setInterval(() => {
            uptimeSeconds++;
            updateElement('#uptime', formatUptime(uptimeSeconds));
        }, 1000);
    }

    function parseUptimeToSeconds(str) {
        let total = 0;
        const dayMatch = str.match(/(\d+)\s*d/);
        const hourMatch = str.match(/(\d+)\s*h/);
        const minMatch = str.match(/(\d+)\s*m/);
        const secMatch = str.match(/(\d+)\s*s/);
        if (dayMatch) total += parseInt(dayMatch[1]) * 86400;
        if (hourMatch) total += parseInt(hourMatch[1]) * 3600;
        if (minMatch) total += parseInt(minMatch[1]) * 60;
        if (secMatch) total += parseInt(secMatch[1]);
        return total || 0;
    }

    function formatUptime(sec) {
        if (sec <= 0) return '-';
        const d = Math.floor(sec / 86400);
        const h = Math.floor((sec % 86400) / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = sec % 60;
        if (d > 0) return `${d}d ${h}h ${m}m`;
        if (h > 0) return `${h}h ${m}m ${s}s`;
        return `${m}m ${s}s`;
    }

    function updateSpeaker(data) {
        const list = $('#speakerList');
        if (!list) return;
        const uid = data.user_id;
        const existing = list.querySelector(`[data-uid="${uid}"]`);
        if (data.speaking) {
            if (!existing) {
                const tag = document.createElement('span');
                tag.className = 'speaker-tag'; tag.dataset.uid = uid;
                tag.innerHTML = `<span class="speaker-dot"></span>${data.user_name || uid}`;
                const muted = list.querySelector('.text-muted');
                if (muted) muted.remove();
                list.appendChild(tag);
            }
        } else {
            if (existing) existing.remove();
            if (list.children.length === 0) list.innerHTML = '<span class="text-muted">无人说话</span>';
        }
    }

    function updateChannel(data) {
        // 多频道模式下，重新加载状态
        loadBotStatus();
    }

    // ==================== 录音列表 ====================
    function loadRecordings() {
        const token = localStorage.getItem('token');
        fetch(`/api/recordings?page=${currentPage}&per_page=${PER_PAGE}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(r => r.json())
            .then(data => {
                const list = $('#recordingList');
                if (!list) return;

                const items = data.items || [];
                totalRecordings = data.total || items.length;
                totalPages = Math.max(1, Math.ceil(totalRecordings / PER_PAGE));

                if (items.length === 0) {
                    list.innerHTML = '<div class="rec-empty">暂无录音</div>';
                } else {
                    list.innerHTML = '';
                    items.forEach(rec => list.appendChild(createRecordingItem(rec)));
                }
                updatePagination();
            })
            .catch(() => {
                const list = $('#recordingList');
                if (list) list.innerHTML = '<div class="rec-empty">加载失败</div>';
            });
    }

    /**
     * 将新录音插入列表顶部（实时推送）
     */
    function prependRecordingItem(data) {
        const list = $('#recordingList');
        if (!list) return;

        // 移除"暂无录音"占位
        const empty = list.querySelector('.rec-empty');
        if (empty) empty.remove();

        // 构造录音对象
        const rec = {
            id: data.id || Date.now(),
            user_name: data.user_name || data.nickname || '未知',
            user_id: data.user_id,
            created_at: data.timestamp || new Date().toISOString(),
            duration: data.duration || 0,
            asr_text: data.asr_text || data.text || '',
            channel_id: data.channel_id || ''
        };

        const item = createRecordingItem(rec);
        item.style.animation = 'fadeIn 0.4s ease';
        list.insertBefore(item, list.firstChild);

        // 保持列表不超过 PER_PAGE 条
        while (list.children.length > PER_PAGE) {
            list.removeChild(list.lastChild);
        }

        // 更新计数
        totalRecordings++;
        totalPages = Math.max(1, Math.ceil(totalRecordings / PER_PAGE));
        updatePagination();
    }

    function updatePagination() {
        const prevBtn = $('#prevPageBtn');
        const nextBtn = $('#nextPageBtn');
        const pageInfo = $('#pageInfo');
        const recCount = $('#recCount');
        if (prevBtn) prevBtn.disabled = currentPage <= 1;
        if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
        if (pageInfo) pageInfo.textContent = `${currentPage} / ${totalPages}`;
        if (recCount) recCount.textContent = `共 ${totalRecordings} 条`;
    }

    function createRecordingItem(rec) {
        const item = document.createElement('div');
        item.className = 'recording-item';
        item.dataset.recId = rec.id;

        const time = rec.created_at || rec.timestamp || '';
        const displayTime = time ? formatTime(time) : '';
        const duration = rec.duration ? `${rec.duration.toFixed(1)}s` : '';
        const name = rec.user_name || rec.nickname || `用户${rec.user_id || ''}`;
        const text = rec.asr_text || rec.transcription || '';
        const channelId = rec.channel_id || '';

        item.innerHTML = `
            <div class="rec-header" onclick="window._liveToggleExpand(this)">
                <div class="rec-meta">
                    <span class="rec-speaker">${name}</span>
                    <span class="rec-time">${displayTime}</span>
                    ${channelId ? `<span class="rec-channel">CH:${channelId}</span>` : ''}
                </div>
                <div class="rec-actions">
                    ${duration ? `<span class="rec-duration">${duration}</span>` : ''}
                    <button class="rec-play-btn" onclick="event.stopPropagation(); window._livePlayAudio(${rec.id}, this)" title="播放">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    </button>
                </div>
            </div>
            ${text ? `<div class="rec-text-preview">${truncate(text, 60)}</div>` : '<div class="rec-text-preview rec-no-text">(未识别)</div>'}
            <div class="rec-expand" style="display:none">
                ${text ? `<div class="rec-text-full">${text}</div>` : ''}
                <div class="rec-player-area" id="player-${rec.id}">
                    <div class="rec-progress-bar" onmousedown="window._liveSeekStart(event, ${rec.id})" ontouchstart="window._liveSeekStart(event, ${rec.id})">
                        <div class="rec-progress-fill" id="progress-${rec.id}"></div>
                    </div>
                    <div class="rec-player-time">
                        <span id="time-cur-${rec.id}">0:00</span>
                        <span id="time-dur-${rec.id}">${duration || '0:00'}</span>
                    </div>
                </div>
            </div>
        `;
        return item;
    }

    // ==================== 录音展开/折叠 ====================
    window._liveToggleExpand = function (header) {
        const item = header.closest('.recording-item');
        const expand = item.querySelector('.rec-expand');
        const isOpen = expand.style.display !== 'none';
        // 先关闭所有
        document.querySelectorAll('.rec-expand').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.recording-item').forEach(el => el.classList.remove('expanded'));
        if (!isOpen) {
            expand.style.display = 'block';
            item.classList.add('expanded');
        }
    };

    // ==================== 录音播放 (fetch+blob) ====================
    window._livePlayAudio = function (id, btn) {
        const token = localStorage.getItem('token');

        // 正在播放同一个 → 暂停
        if (currentPlayingId === id && !globalAudioPlayer.paused) {
            globalAudioPlayer.pause();
            btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
            return;
        }
        // 暂停状态恢复
        if (currentPlayingId === id && globalAudioPlayer.paused) {
            globalAudioPlayer.play();
            btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
            return;
        }

        // 新录音：先展开
        const item = btn.closest('.recording-item');
        const expand = item.querySelector('.rec-expand');
        document.querySelectorAll('.rec-expand').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.recording-item').forEach(el => el.classList.remove('expanded'));
        expand.style.display = 'block';
        item.classList.add('expanded');

        // 重置旧按钮
        resetPlayingState();

        // fetch + blob 带 auth
        btn.innerHTML = '<span class="loading-dot">●</span>';
        fetch(`/api/recordings/${id}/audio`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(r => {
                if (!r.ok) throw new Error('播放失败');
                return r.blob();
            })
            .then(blob => {
                globalAudioPlayer.src = URL.createObjectURL(blob);
                globalAudioPlayer.play();
                currentPlayingId = id;
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';

                globalAudioPlayer.onloadedmetadata = () => {
                    const dur = globalAudioPlayer.duration;
                    const el = document.getElementById(`time-dur-${id}`);
                    if (el) el.textContent = formatDuration(dur);
                };
            })
            .catch(e => {
                showToast('播放失败: ' + e.message, 'error');
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
            });
    };

    function resetPlayingState() {
        if (currentPlayingId) {
            const oldBtn = document.querySelector(`.recording-item[data-rec-id="${currentPlayingId}"] .rec-play-btn`);
            if (oldBtn) {
                oldBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
            }
            const oldFill = document.getElementById(`progress-${currentPlayingId}`);
            if (oldFill) oldFill.style.width = '0%';
        }
        currentPlayingId = null;
    }

    function updateProgressBar() {
        if (!currentPlayingId) return;
        const fill = document.getElementById(`progress-${currentPlayingId}`);
        const curEl = document.getElementById(`time-cur-${currentPlayingId}`);
        if (fill && globalAudioPlayer.duration) {
            const pct = (globalAudioPlayer.currentTime / globalAudioPlayer.duration) * 100;
            fill.style.width = pct + '%';
        }
        if (curEl) curEl.textContent = formatDuration(globalAudioPlayer.currentTime);
    }

    // ==================== Seek 拖动 ====================
    window._liveSeekStart = function (e, id) {
        e.preventDefault();
        const bar = e.currentTarget;

        // 如果尚未播放此录音，先自动开始播放
        if (currentPlayingId !== id) {
            const item = bar.closest('.recording-item');
            const btn = item.querySelector('.rec-play-btn');
            if (btn) {
                window._livePlayAudio(id, btn);
                // 延迟执行 seek（等待音频加载）
                globalAudioPlayer.addEventListener('loadedmetadata', function onMeta() {
                    globalAudioPlayer.removeEventListener('loadedmetadata', onMeta);
                    const rect = bar.getBoundingClientRect();
                    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
                    globalAudioPlayer.currentTime = pct * globalAudioPlayer.duration;
                });
                return;
            }
        }

        const seek = (ev) => {
            const rect = bar.getBoundingClientRect();
            const clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
            const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            if (globalAudioPlayer.duration) {
                globalAudioPlayer.currentTime = pct * globalAudioPlayer.duration;
            }
        };
        seek(e);
        const onMove = (ev) => seek(ev);
        const onEnd = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onEnd);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onEnd);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onEnd);
        document.addEventListener('touchmove', onMove);
        document.addEventListener('touchend', onEnd);
    };

    // ==================== 模式切换 ====================
    let _audioLibLoaded = false;
    window.switchTxMode = function (mode) {
        document.querySelectorAll('.tx-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`.tx-tab[data-mode="${mode}"]`)?.classList.add('active');
        $('#txVoicePanel').style.display = mode === 'voice' ? 'flex' : 'none';
        $('#txTextPanel').style.display = mode === 'text' ? 'flex' : 'none';
        const audioPanel = $('#txAudioPanel');
        if (audioPanel) {
            audioPanel.style.display = mode === 'audio' ? 'flex' : 'none';
            if (mode === 'audio' && !_audioLibLoaded) {
                _audioLibLoaded = true;
                window._loadAudioLib();
            }
        }
    };

    // ==================== 音频库发射 ====================
    // 音频名称截断函数
    function truncateAudioName(name, maxLength = 25) {
        if (!name) return '';
        return name.length > maxLength ? name.substring(0, maxLength) + '...' : name;
    }

    let _selectedAudioId = null;

    window._loadAudioLib = async function () {
        const selectEl = $('#audioLibSelect');
        if (!selectEl) return;
        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/audio-library', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await resp.json();
            const items = data.items || [];
            if (!items.length) {
                selectEl.innerHTML = '<option value="" style="background:#1e2330;color:#9ca3af;">暂无音频文件</option>';
                return;
            }
            selectEl.innerHTML = '<option value="" style="background:#1e2330;color:#9ca3af;">请选择要发射的音频...</option>' + items.map(a => {
                const fullName = a.name || a.filename || '';
                const displayName = truncateAudioName(fullName);
                const durationInfo = a.duration ? ' (' + a.duration + 's)' : '';
                return `<option value="${a.id}"
                        data-name="${fullName.replace(/"/g, '&quot;')}"
                        data-full-name="${fullName.replace(/"/g, '&quot;')}"
                        title="${fullName}${durationInfo}"
                        style="background:#1e2330;color:#e4e6eb;">${displayName}${durationInfo}</option>`;
            }).join('');
        } catch (e) {
            selectEl.innerHTML = '<option value="" style="background:#1e2330;color:#ef4444;">加载失败</option>';
        }
    };

    window._onAudioSelectChange = function () {
        const selectEl = $('#audioLibSelect');
        _selectedAudioId = selectEl.value;
        const btn = $('#audioPlayBtn');
        if (_selectedAudioId) {
            btn.disabled = false;
            btn.style.opacity = '1';
        } else {
            btn.disabled = true;
            btn.style.opacity = '0.5';
        }
    };

    window._playSelectedAudio = async function () {
        if (!_selectedAudioId) return;
        if (!currentChannelId) { showToast('当前未连接任何频道', 'warning'); return; }

        const btn = $('#audioPlayBtn');
        const statusEl = $('#audioPlayStatus');
        const selectEl = $('#audioLibSelect');
        const selectedOption = selectEl.options[selectEl.selectedIndex];
        const selectedName = selectedOption ? selectedOption.dataset.name : '音频';

        btn.disabled = true;
        btn.textContent = '⏳ 发射中...';
        if (statusEl) statusEl.textContent = '正在发射音频...';
        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/bot/play_audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ audio_id: _selectedAudioId, channel_id: currentChannelId })
            });
            const data = await resp.json();
            if (resp.ok && data.success) {
                showToast(`发射完成 (${data.duration}s)`, 'info');
                if (statusEl) statusEl.textContent = `✅ ${data.name} 已发射 ${data.duration}s`;
            } else {
                showToast(data.error || '发射失败', 'error');
                if (statusEl) statusEl.textContent = `❌ ${data.error || '发射失败'}`;
            }
        } catch (e) {
            showToast('请求失败: ' + e.message, 'error');
            if (statusEl) statusEl.textContent = '❌ 请求失败';
        } finally {
            btn.disabled = false;
            btn.textContent = '📡 发射';
        }
    };

    // ==================== TTS 发射 ====================
    window._sendTTSBroadcast = async function () {
        const text = $('#ttsText')?.value.trim();
        if (!text) { showToast('请输入文字', 'warning'); return; }


        const voice = $('#ttsVoice')?.value;
        const speed = parseFloat($('#ttsSpeed')?.value || '1.0');
        const btn = $('#ttsBroadcastBtn');
        const statusEl = $('#ttsStatus');

        btn.disabled = true;
        btn.textContent = '⏳ 合成中...';
        if (statusEl) statusEl.textContent = '正在合成语音并发射...';

        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/bot/tts_broadcast', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ text, voice, speed, channel_id: currentChannelId })
            });
            const data = await resp.json();
            if (resp.ok && data.success) {
                showToast(`发射完成 (${data.duration}s)`, 'info');
                if (statusEl) statusEl.textContent = `✅ 已发射 ${data.duration}s 音频`;
            } else {
                showToast(data.error || '发射失败', 'error');
                if (statusEl) statusEl.textContent = `❌ ${data.error || '发射失败'}`;
            }
        } catch (e) {
            showToast('请求失败: ' + e.message, 'error');
            if (statusEl) statusEl.textContent = `❌ 请求失败`;
        } finally {
            btn.disabled = false;
            btn.textContent = '📡 发射';
        }
    };


    // ==================== 工具函数 ====================
    function updateElement(selector, text) {
        const el = $(selector);
        if (el) el.textContent = text;
    }
    function showToast(msg, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
    function truncate(str, max) {
        return str.length > max ? str.substring(0, max) + '...' : str;
    }
    function formatTime(ts) {
        try {
            // 服务端返回 UTC 时间（无时区后缀），附加 Z 令 JS 按 UTC 解析，getHours 自动转本地时区
            let str = String(ts).replace(' ', 'T');
            if (!str.includes('Z') && !str.includes('+') && !str.includes('-', 11)) str += 'Z';
            const d = new Date(str);
            if (isNaN(d.getTime())) return ts;
            return `${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
        } catch { return ts; }
    }
    function formatDuration(sec) {
        if (!sec || !isFinite(sec)) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    // ==================== 启动 ====================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
