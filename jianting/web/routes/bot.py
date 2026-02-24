"""Bot 状态/控制路由"""

import json
from flask import Blueprint, request, jsonify, g
from web.middleware.auth import token_required, admin_required
from web.models.database import (
    get_bot_status, send_bot_command, add_audit_log
)

bot_bp = Blueprint('bot', __name__)

# 尝试导入共享状态模块
try:
    from src.bot_state import get_bot_state
    HAS_BOT_STATE = True
except ImportError:
    HAS_BOT_STATE = False


@bot_bp.route('/status')
def status():
    """获取 Bot 状态（登录页也需要，不需要认证）"""
    # 优先从共享内存获取状态
    if HAS_BOT_STATE:
        state = get_bot_state()
        if state:
            return jsonify(state.to_dict())

    # 回退到数据库状态
    bot_status = get_bot_status()
    return jsonify({
        'running': bot_status.get('running', 'false') == 'true',
        'channel_id': bot_status.get('channel_id', ''),
        'channel_name': bot_status.get('channel_name', ''),
        'online_count': int(bot_status.get('online_count', 0)),
        'uptime': bot_status.get('uptime', ''),
        'pid': bot_status.get('pid', ''),
        'reconnect_count': int(bot_status.get('reconnect_count', 0)),
    })


@bot_bp.route('/restart', methods=['POST'])
@admin_required
def restart():
    """优雅重启 Bot"""
    cmd_id = send_bot_command('restart', created_by=g.current_user['id'])
    add_audit_log('bot_restart', g.current_user['id'],
                  g.current_user['username'], f'发送重启指令 (cmd_id={cmd_id})',
                  request.remote_addr)
    return jsonify({'success': True, 'command_id': cmd_id})


@bot_bp.route('/logs')
@token_required
def logs():
    """获取 Bot 日志（简化版：读取最近N行日志文件）"""
    import os
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
    lines_count = request.args.get('lines', 100, type=int)
    lines_count = min(lines_count, 500)  # 最多500行

    log_file = os.path.join(log_dir, 'bot.log')
    if not os.path.exists(log_file):
        return jsonify({'logs': [], 'total': 0})

    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()

    recent = all_lines[-lines_count:]
    return jsonify({
        'logs': [line.rstrip() for line in recent],
        'total': len(all_lines)
    })


@bot_bp.route('/search_channels')
@token_required
def search_channels():
    """搜索频道（通过 BSHT API）"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'error': '请提供搜索关键词'})

    # 通过 bot_bridge 获取 listener
    try:
        from web.bot_bridge import get_listener
        listener = get_listener()
    except Exception:
        listener = None

    if not listener:
        return jsonify({'success': False, 'error': 'Bot 未运行或未连接'})

    client = getattr(listener, '_client', None)
    if not client:
        return jsonify({'success': False, 'error': '无法获取 Bot 客户端'})

    result = client.search_channels(query=query)
    if not result.success:
        return jsonify({'success': False, 'error': result.error or '搜索失败'})

    channels = []
    for ch in (result.data or []):
        channels.append({
            'channel_id': ch.channel_id,
            'name': ch.name,
            'user_count': ch.user_count,
            'has_passcode': ch.has_passcode,
        })

    return jsonify({
        'success': True,
        'query': query,
        'channels': channels
    })


@bot_bp.route('/refresh_channels', methods=['POST'])
@admin_required
def refresh_channels():
    """从服务器刷新频道列表"""
    try:
        from web.bot_bridge import get_listener
        listener = get_listener()
    except Exception:
        listener = None

    if not listener:
        return jsonify({'success': False, 'error': 'Bot 未运行或未连接'})

    client = getattr(listener, '_client', None)
    if not client:
        return jsonify({'success': False, 'error': '无法获取 Bot 客户端'})

    result = client.search_channels(query='', limit=200)
    if not result.success:
        return jsonify({'success': False, 'error': result.error or '获取失败'})

    # 保存到数据库
    from web.models.database import db_execute
    saved = 0
    for ch in (result.data or []):
        try:
            db_execute(
                """INSERT OR REPLACE INTO channels (channel_id, name, passcode, auto_join)
                   VALUES (?, ?, 0, 0)""",
                (ch.channel_id, ch.name)
            )
            saved += 1
        except Exception:
            pass

    add_audit_log('refresh_channels', g.current_user['id'],
                  g.current_user['username'], f'刷新频道列表，保存 {saved} 个',
                  request.remote_addr)

    return jsonify({'success': True, 'saved_count': saved})


@bot_bp.route('/tts_broadcast', methods=['POST'])
@token_required
def tts_broadcast():
    """TTS 合成并发射到频道"""
    import asyncio
    import wave
    import io
    import time as _time
    import numpy as np

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    voice = data.get('voice')
    speed = data.get('speed')

    if not text:
        return jsonify({'error': '请输入要发射的文本'}), 400
    if len(text) > 500:
        return jsonify({'error': '文本长度不能超过 500 字符'}), 400

    # 获取 listener
    from web.bot_bridge import get_bot_listener
    listener = get_bot_listener()
    if not listener:
        return jsonify({'error': 'Bot 未连接'}), 503

    try:
        # 1. TTS 合成
        from src.tts_module import TTSEngine
        engine = TTSEngine()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_data = loop.run_until_complete(engine.synthesize(text, voice, speed))
        finally:
            loop.close()

        if not audio_data:
            return jsonify({'error': 'TTS 合成失败：无数据返回'}), 500

        # 2. 音频 → PCM (支持 WAV / MP3 / 其他格式)
        pcm, src_rate = _decode_audio_to_pcm(audio_data)
        if pcm is None:
            return jsonify({'error': '无法解析 TTS 返回的音频格式'}), 500

        # 3. 发射
        duration, frame_count = _broadcast_pcm(pcm, src_rate, listener)

        return jsonify({
            'success': True,
            'duration': duration,
            'frames': frame_count,
            'text': text[:50]
        })

    except RuntimeError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        try:
            listener.stop_transmit_web()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'TTS 发射失败: {str(e)}'}), 500


def _decode_audio_to_pcm(audio_data: bytes):
    """将音频数据解码为 PCM int16 单声道。返回 (pcm_array, sample_rate) 或 (None, 0)"""
    import numpy as np
    import wave
    import io

    # 尝试 WAV
    if audio_data[:4] == b'RIFF':
        try:
            with wave.open(io.BytesIO(audio_data), 'rb') as wf:
                src_rate = wf.getframerate()
                src_channels = wf.getnchannels()
                src_width = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())
            if src_width == 2:
                pcm = np.frombuffer(raw, dtype=np.int16)
            elif src_width == 1:
                pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) * 256
            else:
                return None, 0
            if src_channels > 1:
                pcm = pcm.reshape(-1, src_channels).mean(axis=1).astype(np.int16)
            return pcm, src_rate
        except Exception:
            pass

    # 尝试用 pydub 解码（支持 MP3/OGG 等）
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        seg = seg.set_channels(1).set_sample_width(2)
        pcm = np.frombuffer(seg.raw_data, dtype=np.int16)
        return pcm, seg.frame_rate
    except Exception:
        pass

    # 尝试用 ffmpeg subprocess
    try:
        import subprocess
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.audio', delete=False) as tmp_in:
            tmp_in.write(audio_data)
            tmp_path = tmp_in.name
        out_path = tmp_path + '.wav'
        try:
            subprocess.run([
                'ffmpeg', '-y', '-i', tmp_path,
                '-ar', '48000', '-ac', '1', '-sample_fmt', 's16',
                out_path
            ], capture_output=True, timeout=30)
            with wave.open(out_path, 'rb') as wf:
                pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                return pcm, wf.getframerate()
        finally:
            for p in [tmp_path, out_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass
    except Exception:
        pass

    return None, 0


def _broadcast_pcm(pcm, src_rate: int, listener):
    """将 PCM 数据重采样到 48kHz 并以实时速率发射。返回 (duration, frame_count)"""
    import time as _time
    import numpy as np

    TARGET_RATE = 48000
    FRAME_SIZE = 960
    FRAME_INTERVAL = 0.02

    if src_rate != TARGET_RATE:
        n_target = int(len(pcm) * TARGET_RATE / src_rate)
        indices = np.linspace(0, len(pcm) - 1, n_target)
        pcm = np.interp(indices, np.arange(len(pcm)), pcm.astype(np.float64)).astype(np.int16)

    duration = len(pcm) / TARGET_RATE

    success = listener.start_transmit_web()
    if not success:
        raise RuntimeError('发射启动失败（可能正在发射中）')

    try:
        offset = 0
        frame_count = 0
        t0 = _time.monotonic()
        while offset + FRAME_SIZE <= len(pcm):
            frame = np.ascontiguousarray(pcm[offset:offset + FRAME_SIZE])
            listener.feed_web_pcm(frame.tobytes())
            offset += FRAME_SIZE
            frame_count += 1
            next_time = t0 + frame_count * FRAME_INTERVAL
            sleep_dur = next_time - _time.monotonic()
            if sleep_dur > 0:
                _time.sleep(sleep_dur)
    finally:
        listener.stop_transmit_web()

    return round(duration, 1), frame_count


@bot_bp.route('/play_audio', methods=['POST'])
@token_required
def play_audio():
    """播放音频库文件并发射到频道"""
    import os

    data = request.get_json() or {}
    audio_id = data.get('audio_id')

    if not audio_id:
        return jsonify({'error': '请选择音频文件'}), 400

    # 查询音频文件
    from web.models.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, filepath FROM audio_library WHERE id = ?", (audio_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': '音频不存在'}), 404
    if not os.path.exists(row['filepath']):
        return jsonify({'error': '音频文件不存在'}), 404

    # 获取 listener
    from web.bot_bridge import get_bot_listener
    listener = get_bot_listener()
    if not listener:
        return jsonify({'error': 'Bot 未连接'}), 503

    try:
        with open(row['filepath'], 'rb') as f:
            audio_data = f.read()

        pcm, src_rate = _decode_audio_to_pcm(audio_data)
        if pcm is None:
            return jsonify({'error': '无法解析音频格式'}), 500

        duration, frame_count = _broadcast_pcm(pcm, src_rate, listener)

        # 增加使用次数
        conn = get_db()
        conn.execute("UPDATE audio_library SET use_count = use_count + 1 WHERE id = ?", (audio_id,))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'duration': duration,
            'frames': frame_count,
            'name': row['name']
        })

    except RuntimeError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        try:
            listener.stop_transmit_web()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'音频发射失败: {str(e)}'}), 500
