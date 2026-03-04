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
    获取音频时长

    Args:
        file_path: 音频文件路径

    Returns:
        时长（秒），如果无法获取则返回 None
    """
    try:
        import wave
        import struct

        # 尝试用 wave 模块读取（适用于 WAV）
        try:
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                return duration
        except:
            pass

        # 对于其他格式，尝试使用 mutagen（如果安装）
        try:
            from mutagen import File as MutagenFile
            audio_file = MutagenFile(file_path)
            if audio_file is not None and audio_file.info:
                return audio_file.info.length
        except ImportError:
            pass
        except:
            pass

        # 如果都失败，返回 None
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

    # 解析 JSON 请求体
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的请求数据")

    audio_data = data.get('data')
    filename = data.get('filename')
    description = data.get('description')
    duration = data.get('duration')

    if not audio_data:
        raise HTTPException(status_code=400, detail="无效的音频数据：缺少 data 字段")

    # 解析 base64 数据
    try:
        # Web Audio API 录音通常是 WebM 格式
        data_url = audio_data
        if ',' in data_url:
            header, base64_data = data_url.split(',', 1)
        else:
            base64_data = data_url

        file_content = base64.b64decode(base64_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"音频数据解码失败: {str(e)}")

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"录音太大。最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if filename:
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
    else:
        safe_filename = f"recording_{timestamp}"

    filename = f"{safe_filename}.webm"

    # 保存文件
    file_path = UPLOAD_DIR / filename
    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 获取音频时长
    duration = audio_data.get('duration')

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
            'recording',
            description,
            duration,
            len(file_content),
            '{"browser_recorded": true}',
            1,
            now
        ))

        item_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "保存成功",
            "data": {
                "id": item_id,
                "filename": filename,
                "filepath": str(file_path),
                "duration": duration
            }
        }
    except Exception as e:
        conn.rollback()
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")
    finally:
        conn.close()
