/**
 * AudioTransmitter — Web 端麦克风采集与 PTT 发射
 *
 * 支持两种模式：
 * - Socket.IO 模式 (默认): 通过 Socket.IO 发送音频
 * - WebRTC 模式: 通过 WebRTC DataChannel 发送音频
 *
 * 麦克风流常驻（首次获取后不释放），PTT 仅切换音频图连接。
 * 消除 getUserMedia 延迟导致的首帧漏音。
 */
class AudioTransmitter {
    constructor(socket, useWebRTC = false) {
        this.socket = socket;
        this.useWebRTC = useWebRTC;
        this.webrtc = null;
        this.audioCtx = null;
        this.captureNode = null;
        this.sourceNode = null;
        this.mediaStream = null;
        this.isTransmitting = false;
        this._frameCount = 0;
        this._workletReady = false;
    }

    /**
     * 确保 WebRTC 连接已建立
     */
    async _ensureWebRTC() {
        if (this.webrtc && this.webrtc.isConnected) {
            return;
        }
        this.webrtc = new WebRTCAudioTransmitter();
        await this.webrtc.connect();
    }

    /**
     * 确保 AudioContext 和 Worklet 只初始化一次
     */
    async _ensureAudioContext() {
        if (this.audioCtx && this.audioCtx.state !== 'closed' && this._workletReady) {
            if (this.audioCtx.state === 'suspended') {
                await this.audioCtx.resume();
            }
            return;
        }

        this.audioCtx = new AudioContext({ sampleRate: 48000 });
        await this.audioCtx.audioWorklet.addModule('/static/js/pcm-capture.worklet.js?v=' + Date.now());
        this._workletReady = true;
        console.log('[AudioTransmitter] AudioContext 和 Worklet 已初始化');
    }

    /**
     * 确保麦克风流常驻（首次获取后复用）
     */
    async _ensureMediaStream() {
        // 检查已有流是否仍然有效
        if (this.mediaStream) {
            const track = this.mediaStream.getAudioTracks()[0];
            if (track && track.readyState === 'live') {
                return; // 流仍可用，复用
            }
            // 流已失效，清理
            this.mediaStream = null;
            this.sourceNode = null;
        }

        // 首次获取麦克风
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 48000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        // 创建源节点（绑定到常驻流）
        this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
        console.log('[AudioTransmitter] 麦克风流已获取');
    }

    /**
     * 发送音频数据 (根据模式选择)
     */
    _sendAudio(mergedBuffer) {
        if (this.useWebRTC && this.webrtc) {
            // WebRTC 模式
            this.webrtc.sendAudioFrame(mergedBuffer);
        } else {
            // Socket.IO 模式 (默认)
            this.socket.emit('ptt:audio', mergedBuffer);
        }
    }

    /**
     * 开始发射 (按下 PTT)
     * @param {number|string} channelId - 目标频道 ID
     */
    async startTransmit(channelId) {
        if (this.isTransmitting) return;

        try {
            // 如果使用 WebRTC，先建立连接
            if (this.useWebRTC) {
                await this._ensureWebRTC();
            }

            await this._ensureAudioContext();
            await this._ensureMediaStream();

            // 创建采集节点（每次 PTT 新建，确保干净状态）
            this.captureNode = new AudioWorkletNode(this.audioCtx, 'pcm-capture');
            this._frameCount = 0;
            this._pcmBuffer = [];  // 缓冲多帧后批量发送
            this._FRAMES_PER_EMIT = 5;  // 每 5 帧发送一次 (100ms)，提高稳定性
            this.captureNode.port.onmessage = (e) => {
                if (this.isTransmitting && e.data.type === 'pcm') {
                    this._pcmBuffer.push(e.data.samples);
                    this._frameCount++;
                    if (this._pcmBuffer.length >= this._FRAMES_PER_EMIT) {
                        // 合并多帧为一个 ArrayBuffer 发送
                        const totalLen = this._pcmBuffer.reduce((s, a) => s + a.length, 0);
                        const merged = new Int16Array(totalLen);
                        let offset = 0;
                        for (const frame of this._pcmBuffer) {
                            merged.set(frame, offset);
                            offset += frame.length;
                        }
                        this._sendAudio(merged.buffer);
                        this._pcmBuffer = [];
                    }
                }
            };

            // 连接音频图：mic → capture worklet
            this.sourceNode.connect(this.captureNode);

            // 通知服务器
            if (!this.useWebRTC) {
                this.socket.emit('ptt:start', { channel_id: channelId });
            }
            this.isTransmitting = true;
            console.log(`[AudioTransmitter] 发射已启动 (channel=${channelId}, mode=${this.useWebRTC ? 'WebRTC' : 'Socket.IO'})`);
        } catch (e) {
            console.error('[AudioTransmitter] 启动失败:', e);
            this._stopCapture();
            throw e;
        }
    }

    /**
     * 停止发射 (松开 PTT)
     */
    stopTransmit() {
        if (!this.isTransmitting) return;
        this.isTransmitting = false;

        // 刷新缓冲区中的剩余帧
        if (this._pcmBuffer && this._pcmBuffer.length > 0) {
            const totalLen = this._pcmBuffer.reduce((s, a) => s + a.length, 0);
            const merged = new Int16Array(totalLen);
            let offset = 0;
            for (const frame of this._pcmBuffer) {
                merged.set(frame, offset);
                offset += frame.length;
            }
            this._sendAudio(merged.buffer);
            this._pcmBuffer = [];
        }

        if (!this.useWebRTC) {
            this.socket.emit('ptt:stop');
        }
        console.log(`[AudioTransmitter] 发射已停止 (${this._frameCount} 帧)`);
        this._stopCapture();
    }

    /**
     * 停止采集（断开音频图连接，但不释放麦克风流）
     */
    _stopCapture() {
        if (this.sourceNode && this.captureNode) {
            try { this.sourceNode.disconnect(this.captureNode); } catch (e) { /* 可能已断开 */ }
        }
        if (this.captureNode) {
            this.captureNode.disconnect();
            this.captureNode = null;
        }
        // 注意：不释放 mediaStream 和 sourceNode，下次 PTT 复用
    }

    /**
     * 完全释放所有资源（页面离开时调用）
     */
    dispose() {
        this._stopCapture();
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(t => t.stop());
            this.mediaStream = null;
        }
        if (this.sourceNode) {
            this.sourceNode.disconnect();
            this.sourceNode = null;
        }
        if (this.audioCtx && this.audioCtx.state !== 'closed') {
            this.audioCtx.close();
            this.audioCtx = null;
        }
        // 清理 WebRTC 连接
        if (this.webrtc) {
            this.webrtc.disconnect();
            this.webrtc = null;
        }
        this._workletReady = false;
    }
}

if (typeof window !== 'undefined') {
    window.AudioTransmitter = AudioTransmitter;
}
