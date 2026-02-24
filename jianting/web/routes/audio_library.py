"""常用音频库路由"""

import os
import asyncio
from flask import Blueprint, request, jsonify, g, send_file, current_app
from werkzeug.utils import secure_filename
from web.middleware.auth import token_required, admin_required, can_listen_recordings_required
from web.models.database import get_db, add_audit_log

audio_library_bp = Blueprint('audio_library', __name__)

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg', 'opus'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_upload_dir():
    """获取音频上传目录"""
    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'data', 'audio_library'
    )
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@audio_library_bp.route('')
@can_listen_recordings_required
def list_audio():
    """获取音频库列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, filename, duration, file_size, use_count, uploaded_by, source_type, voice, tts_text, created_at
        FROM audio_library ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'items': [dict(row) for row in rows]})


@audio_library_bp.route('', methods=['POST'])
@admin_required
def upload_audio():
    """上传音频文件"""
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未选择文件'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'error': f'仅支持 {", ".join(ALLOWED_EXTENSIONS)} 格式'}), 400

    name = request.form.get('name', '').strip()
    if not name:
        name = os.path.splitext(file.filename)[0]

    filename = secure_filename(file.filename)
    # 避免重名
    upload_dir = _get_upload_dir()
    filepath = os.path.join(upload_dir, filename)
    counter = 1
    base, ext = os.path.splitext(filename)
    while os.path.exists(filepath):
        filename = f"{base}_{counter}{ext}"
        filepath = os.path.join(upload_dir, filename)
        counter += 1

    file.save(filepath)
    file_size = os.path.getsize(filepath)

    if file_size > MAX_FILE_SIZE:
        os.remove(filepath)
        return jsonify({'error': '文件大小超过 10MB 限制'}), 400

    # 尝试获取音频时长
    duration = 0
    try:
        import wave
        with wave.open(filepath, 'r') as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = round(frames / rate, 1)
    except Exception:
        pass

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audio_library (name, filename, filepath, duration, file_size, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, filename, filepath, duration, file_size, g.current_user['username']))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    add_audit_log('upload_audio', g.current_user['id'],
                  g.current_user['username'],
                  f'上传音频 {name} ({filename})',
                  request.remote_addr)

    return jsonify({'success': True, 'id': new_id}), 201


@audio_library_bp.route('/<int:audio_id>/play')
@can_listen_recordings_required
def play_audio(audio_id):
    """预览播放音频"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, filename FROM audio_library WHERE id = ?", (audio_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': '音频不存在'}), 404

    if not os.path.exists(row['filepath']):
        return jsonify({'error': '文件不存在'}), 404

    mimetype = 'audio/wav'
    if row['filename'].endswith('.mp3'):
        mimetype = 'audio/mpeg'
    elif row['filename'].endswith('.ogg') or row['filename'].endswith('.opus'):
        mimetype = 'audio/ogg'

    return send_file(row['filepath'], mimetype=mimetype)


@audio_library_bp.route('/<int:audio_id>', methods=['DELETE'])
@admin_required
def delete_audio(audio_id):
    """删除音频"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, filepath FROM audio_library WHERE id = ?", (audio_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': '音频不存在'}), 404

    # 删除文件
    if os.path.exists(row['filepath']):
        os.remove(row['filepath'])

    cursor.execute("DELETE FROM audio_library WHERE id = ?", (audio_id,))
    conn.commit()
    conn.close()

    add_audit_log('delete_audio', g.current_user['id'],
                  g.current_user['username'],
                  f'删除音频 {row["name"]}',
                  request.remote_addr)

    return jsonify({'success': True})


@audio_library_bp.route('/<int:audio_id>', methods=['PUT'])
@admin_required
def update_audio(audio_id):
    """更新音频信息"""
    data = request.get_json() or {}
    new_name = data.get('name', '').strip()
    rename_file = data.get('rename_file', False)

    if not new_name:
        return jsonify({'error': '请输入音频名称'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, filename, filepath FROM audio_library WHERE id = ?", (audio_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': '音频不存在'}), 404

    old_name = row['name']
    old_filename = row['filename']
    old_filepath = row['filepath']

    # 如果需要重命名文件
    if rename_file and old_filename:
        # 获取扩展名
        ext = os.path.splitext(old_filename)[1]
        new_filename = new_name + ext
        new_filepath = os.path.join(os.path.dirname(old_filepath), new_filename)

        # 检查新文件名是否已存在
        if os.path.exists(new_filepath) and new_filepath != old_filepath:
            conn.close()
            return jsonify({'error': '文件名已存在'}), 400

        # 重命名文件
        try:
            os.rename(old_filepath, new_filepath)
        except Exception as e:
            conn.close()
            return jsonify({'error': f'重命名文件失败: {str(e)}'}), 500

        cursor.execute("""
            UPDATE audio_library SET name = ?, filename = ?, filepath = ? WHERE id = ?
        """, (new_name, new_filename, new_filepath, audio_id))
    else:
        cursor.execute("UPDATE audio_library SET name = ? WHERE id = ?", (new_name, audio_id))

    conn.commit()
    conn.close()

    add_audit_log('update_audio', g.current_user['id'],
                  g.current_user['username'],
                  f'更新音频 {old_name} -> {new_name}',
                  request.remote_addr)

    return jsonify({'success': True})


@audio_library_bp.route('/<int:audio_id>/use', methods=['POST'])
@can_listen_recordings_required
def increment_use(audio_id):
    """增加使用次数（发射后调用）"""
    conn = get_db()
    conn.execute("UPDATE audio_library SET use_count = use_count + 1 WHERE id = ?", (audio_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ========== TTS 相关接口 ==========

@audio_library_bp.route('/voices')
@can_listen_recordings_required
def list_voices():
    """获取可用声音列表"""
    from src.tts_module import TTSEngine
    voices = TTSEngine.get_voices()
    return jsonify({
        'voices': [{'id': vid, 'name': name} for vid, name in voices],
        'default_voice': TTSEngine(None).default_voice,
        'default_speed': TTSEngine(None).default_speed
    })


@audio_library_bp.route('/preview', methods=['POST'])
@can_listen_recordings_required
def preview_tts():
    """生成试听音频 (返回 base64)"""
    from src.tts_module import TTSEngine

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    voice = data.get('voice')
    speed = data.get('speed')

    if not text:
        return jsonify({'error': '请输入要合成的文本'}), 400

    if len(text) > 1000:
        return jsonify({'error': '文本长度不能超过 1000 字符'}), 400

    try:
        engine = TTSEngine()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            base64_audio = loop.run_until_complete(engine.preview(text, voice, speed))
        finally:
            loop.close()

        return jsonify({
            'audio': base64_audio,
            'format': 'wav'
        })
    except Exception as e:
        return jsonify({'error': f'TTS 合成失败: {str(e)}'}), 500


@audio_library_bp.route('/tts', methods=['POST'])
@admin_required
def create_tts():
    """TTS 生成并保存到音频库"""
    from src.tts_module import TTSEngine

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    voice = data.get('voice')
    speed = data.get('speed')
    name = data.get('name', '').strip()

    if not text:
        return jsonify({'error': '请输入要合成的文本'}), 400

    if len(text) > 1000:
        return jsonify({'error': '文本长度不能超过 1000 字符'}), 400

    if not name:
        name = text[:50] + ('...' if len(text) > 50 else '')

    try:
        engine = TTSEngine()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            wav_data = loop.run_until_complete(engine.synthesize(text, voice, speed))
        finally:
            loop.close()

        # 保存文件
        filepath, duration, file_size = engine.save_to_file(wav_data, name)
        filename = os.path.basename(filepath)

        # 获取实际使用的 voice
        actual_voice = voice or engine.default_voice

        # 保存到数据库
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audio_library (name, filename, filepath, duration, file_size, uploaded_by, source_type, voice, tts_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, filename, filepath, duration, file_size, g.current_user['username'], 'tts', actual_voice, text))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        add_audit_log('create_tts', g.current_user['id'],
                      g.current_user['username'],
                      f'TTS 合成音频 {name}',
                      request.remote_addr)

        return jsonify({
            'success': True,
            'id': new_id,
            'name': name,
            'duration': duration,
            'file_size': file_size
        })
    except Exception as e:
        return jsonify({'error': f'TTS 生成失败: {str(e)}'}), 500


# ========== 录音相关接口 ==========

@audio_library_bp.route('/record', methods=['POST'])
@admin_required
def save_record():
    """保存录音到音频库"""
    data = request.get_json() or {}
    audio_data = data.get('audio')  # base64 编码的音频
    name = data.get('name', '').strip()
    duration = data.get('duration', 0)

    if not audio_data:
        return jsonify({'error': '请提供录音数据'}), 400

    import base64
    try:
        wav_data = base64.b64decode(audio_data)
    except Exception:
        return jsonify({'error': '无效的音频数据'}), 400

    if not name:
        from datetime import datetime
        name = f"录音_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 确保是 WAV 扩展名
    if not name.lower().endswith('.wav'):
        name += '.wav'

    # 保存文件
    upload_dir = _get_upload_dir()
    filepath = os.path.join(upload_dir, name)

    # 避免重名
    counter = 1
    base, ext = os.path.splitext(name)
    while os.path.exists(filepath):
        name = f"{base}_{counter}{ext}"
        filepath = os.path.join(upload_dir, name)
        counter += 1

    with open(filepath, 'wb') as f:
        f.write(wav_data)

    file_size = len(wav_data)

    # 保存到数据库
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audio_library (name, filename, filepath, duration, file_size, uploaded_by, source_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, name, filepath, duration, file_size, g.current_user['username'], 'record'))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    add_audit_log('save_record', g.current_user['id'],
                  g.current_user['username'],
                  f'保存录音 {name}',
                  request.remote_addr)

    return jsonify({
        'success': True,
        'id': new_id,
        'name': name,
        'duration': duration,
        'file_size': file_size
    })
