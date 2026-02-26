/**
 * WebRTC 音频发射客户端
 *
 * 使用 RTCDataChannel 发送音频数据
 */

class WebRTCAudioTransmitter {
    constructor() {
        this.pc = null;
        this.dataChannel = null;
        this.isConnected = false;
    }

    /**
     * 建立 WebRTC 连接
     */
    async connect() {
        // 创建 RTCPeerConnection
        this.pc = new RTCPeerConnection({
            iceServers: []  // 不需要 TURN
        });

        // 创建 DataChannel (可靠模式)
        this.dataChannel = this.pc.createDataChannel('audio', {
            ordered: true,
            maxRetransmits: 30
        });

        this.dataChannel.onopen = () => {
            console.log('[WebRTC] DataChannel 已打开');
            this.isConnected = true;
        };

        this.dataChannel.onclose = () => {
            console.log('[WebRTC] DataChannel 已关闭');
            this.isConnected = false;
        };

        this.dataChannel.onerror = (err) => {
            console.error('[WebRTC] DataChannel 错误:', err);
        };

        // 创建并发送 offer
        const offer = await this.pc.createOffer();
        await this.pc.setLocalDescription(offer);

        // 发送到服务器获取 answer
        const response = await fetch('/api/webrtc/offer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sdp: offer.sdp })
        });

        if (!response.ok) {
            throw new Error('WebRTC 连接失败');
        }

        const { sdp, type } = await response.json();
        if (sdp) {
            await this.pc.setRemoteDescription({ sdp, type });
        }

        console.log('[WebRTC] 连接已建立');
    }

    /**
     * 发送音频帧
     * @param {ArrayBuffer|Int16Array} audioData - 音频数据
     */
    sendAudioFrame(audioData) {
        if (!this.isConnected || !this.dataChannel) {
            return false;
        }

        // 检查 DataChannel 状态
        if (this.dataChannel.readyState !== 'open') {
            return false;
        }

        try {
            this.dataChannel.send(audioData);
            return true;
        } catch (err) {
            console.error('[WebRTC] 发送失败:', err);
            return false;
        }
    }

    /**
     * 断开连接
     */
    async disconnect() {
        if (this.dataChannel) {
            this.dataChannel.close();
            this.dataChannel = null;
        }
        if (this.pc) {
            await this.pc.close();
            this.pc = null;
        }
        this.isConnected = false;
        console.log('[WebRTC] 已断开连接');
    }
}

if (typeof window !== 'undefined') {
    window.WebRTCAudioTransmitter = WebRTCAudioTransmitter;
}
