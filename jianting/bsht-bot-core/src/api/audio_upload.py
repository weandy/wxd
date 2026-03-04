"""
音频上传 API
支持上传音频文件到音频库
"""
import os
import shutil
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from src.database import Database


router = APIRouter()

# 上传目录配置
UPLOAD_DIR = Path("audio_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 支持的音频格式
SUPPORTED_FORMATS = {
    'audio/opus': '.opus',
    'audio/wav': '.wav',
    'audio/wave': '.wav',
    'audio/mpeg': '.mp3',
    'audio/mp3': '.mp3',
    'audio/x-wav': '.wav',
    'audio/x-mpeg': '.mp3',
}

# 最大文件大小 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    message: str
    data: Optional[dict] = None


def get_db():
    """获取数据库实例"""
    return Database()


def get_audio_duration(file_path: str) -> Optional[float]:
    """
    获取音频时长（支持多种格式）

    Args:
        file_path: 音频文件路径

    Returns:
        时长（秒），如果无法获取则返回 None
    """
    try:
        import subprocess
        import json

        # ✅ 方案1: 使用 ffprobe (最准确，支持所有格式)
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'json',
                str(file_path)
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get('format', {}).get('duration', 0))
                if duration > 0:
                    return duration
        except (subprocess.SubprocessError, json.JSONDecodeError, ValueError):
            pass

        # ✅ 方案2: wave 模块 (WAV 格式)
        try:
            import wave
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                if duration > 0:
                    return duration
        except:
            pass

        # ✅ 方案3: mutagen (备用)
        try:
            from mutagen import File as MutagenFile
            audio_file = MutagenFile(file_path)
            if audio_file is not None and audio_file.info:
                duration = audio_file.info.length
                if duration > 0:
                    return duration
        except ImportError:
            pass
        except:
            pass

        return None
    except Exception:
        return None


@router.post("/audio-library/upload")
async def upload_audio(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    source_type: str = Form("upload"),
    db: Database = Depends(get_db)
):
    """
    上传音频文件到音频库

    Args:
        file: 上传的音频文件
        description: 音频描述
        source_type: 来源类型（upload/recording/tts）
        db: 数据库实例

    Returns:
        上传结果
    """
    import sqlite3

    # 验证文件类型
    if file.content_type not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。支持的格式: {', '.join(SUPPORTED_FORMATS.keys())}"
        )

    # 读取文件内容
    file_content = await file.read()

    # 检查文件大小
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件太大。最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # 获取文件扩展名
    file_extension = SUPPORTED_FORMATS.get(file.content_type, '.opus')

    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = f"{timestamp}_{file.filename.rsplit('.', 1)[0] if '.' in file.filename else 'audio'}"
    safe_filename = "".join(c for c in filename_base if c.isalnum() or c in ('_', '-', '.'))
    filename = f"{safe_filename}{file_extension}"

    # 保存文件
    file_path = UPLOAD_DIR / filename
    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 获取音频时长
    duration = get_audio_duration(str(file_path))

    # 保存到数据库
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO audio_library (filename, filepath, source_type, description, duration, file_size, metadata, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename,
            str(file_path),
            source_type,
            description,
            duration,
            len(file_content),
            '{"uploaded": true}',
            1,  # 默认创建者为ID=1的用户
            now
        ))

        item_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "上传成功",
            "data": {
                "id": item_id,
                "filename": filename,
                "filepath": str(file_path),
                "duration": duration,
                "file_size": len(file_content)
            }
        }
    except Exception as e:
        conn.rollback()
        # 删除已上传的文件
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")
    finally:
        conn.close()


@router.get("/audio-library/formats")
async def get_supported_formats():
    """
    获取支持的音频格式列表

    Returns:
        支持的格式信息
    """
    return {
        "code": 0,
        "message": "success",
        "data": {
            "formats": list(SUPPORTED_FORMATS.keys()),
            "extensions": list(set(SUPPORTED_FORMATS.values())),
            "max_file_size": MAX_FILE_SIZE,
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024)
        }
    }


@router.post("/audio-library/record")
async def save_browser_recording(
    request: Request,
    db: Database = Depends(get_db)
):
    """
    保存浏览器录制的音频

    Args:
        request: FastAPI 请求对象
        db: 数据库实例

    Returns:
        保存结果
    """
    import base64
    import sqlite3
    import logging

    logger = logging.getLogger(__name__)

    # 解析 JSON 请求体
    try:
        data = await request.json()
        logger.info(f"[录音保存] 收到请求数据: keys={list(data.keys())}")
    except Exception as e:
        logger.error(f"[录音保存] JSON 解析失败: {e}")
        raise HTTPException(status_code=400, detail="无效的请求数据")

    audio_data = data.get('data')
    filename = data.get('filename')
    description = data.get('description')
    duration = data.get('duration')

    logger.info(f"[录音保存] filename={filename}, duration={duration}, has_data={bool(audio_data)}")

    if not audio_data:
        logger.error("[录音保存] 缺少 audio_data")
        raise HTTPException(status_code=400, detail="无效的音频数据：缺少 data 字段")

    # 解析 base64 数据
    try:
        # Web Audio API 录音通常是 WebM 格式
        data_url = audio_data
        if ',' in data_url:
            header, base64_data = data_url.split(',', 1)
            logger.info(f"[录音保存] 数据格式: {header[:50]}...")
        else:
            base64_data = data_url
            logger.info(f"[录音保存] 纯 base64 数据")

        file_content = base64.b64decode(base64_data)
        logger.info(f"[录音保存] 解码成功: {len(file_content)} bytes")
    except Exception as e:
        logger.error(f"[录音保存] base64 解码失败: {e}")
        raise HTTPException(status_code=400, detail=f"音频数据解码失败: {str(e)}")

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"录音太大。最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # 生成基础文件名（去掉用户可能传入的扩展名，避免 .webm.webm）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if filename:
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
        for ext in ('.webm', '.wav', '.mp3', '.opus', '.m4a', '.ogg'):
            if safe_filename.lower().endswith(ext):
                safe_filename = safe_filename[:-len(ext)]
                break
        if not safe_filename:
            safe_filename = f"recording_{timestamp}"
    else:
        safe_filename = f"recording_{timestamp}"

    # 先落地原始录音，再统一转成可直接发射的 WAV（48kHz/单声道/16-bit PCM）
    raw_filename = f"{safe_filename}.webm"
    raw_file_path = UPLOAD_DIR / raw_filename

    wav_filename = f"{safe_filename}.wav"
    wav_file_path = UPLOAD_DIR / wav_filename

    logger.info(f"[录音保存] 保存原始文件到: {raw_file_path}")
    try:
        with open(raw_file_path, 'wb') as f:
            f.write(file_content)
        logger.info("[录音保存] 原始文件保存成功")
    except Exception as e:
        logger.error(f"[录音保存] 原始文件保存失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 转换为发射兼容 WAV
    try:
        import subprocess
        subprocess.run([
            'ffmpeg', '-y', '-i', str(raw_file_path),
            '-ar', '48000',
            '-ac', '1',
            '-acodec', 'pcm_s16le',
            str(wav_file_path)
        ], check=True, capture_output=True)
        logger.info(f"[录音保存] WAV 转换成功: {wav_file_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"[录音保存] ffmpeg 转换失败: {e}")
        stderr_text = e.stderr.decode(errors='ignore') if e.stderr else str(e)
        raise HTTPException(status_code=500, detail=f"音频转 WAV 失败: {stderr_text[:200]}")
    except FileNotFoundError:
        logger.error("[录音保存] ffmpeg 未安装或不在 PATH")
        raise HTTPException(status_code=500, detail="服务器未安装 ffmpeg，无法转换为 WAV")

    # 删除原始 webm，仅保留可直接发射的 wav
    try:
        if raw_file_path.exists():
            raw_file_path.unlink()
    except Exception:
        pass

    # 获取音频时长（以转换后的 WAV 为准）
    duration = data.get('duration') or get_audio_duration(str(wav_file_path))


    # 保存到数据库
    logger.info(f"[录音保存] 开始保存到数据库...")
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO audio_library (filename, filepath, source_type, description, duration, file_size, metadata, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            wav_filename,
            str(wav_file_path),
            'recording',
            description,
            duration,
            len(file_content),
            '{"browser_recorded": true, "converted_to_wav": true, "sample_rate": 48000, "channels": 1, "codec": "pcm_s16le"}',
            1,
            now
        ))

        item_id = cursor.lastrowid
        conn.commit()
        logger.info(f"[录音保存] 数据库保存成功: id={item_id}")

        return {
            "code": 0,
            "message": "保存成功",
            "data": {
                "id": item_id,
                "filename": wav_filename,
                "filepath": str(wav_file_path),
                "duration": duration
            }
        }
    except Exception as e:
        logger.error(f"[录音保存] 数据库保存失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        conn.rollback()
        if wav_file_path.exists():
            wav_file_path.unlink()
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")
    finally:
        conn.close()
