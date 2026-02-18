"""
数据库模块 - SQLite存储音频识别结果
高内聚低耦合设计
"""
import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class AudioRecord:
    """音频识别记录"""
    id: Optional[int] = None
    timestamp: str = ""
    channel_id: int = 0
    user_id: int = 0
    nickname: str = ""
    
    # 音频质量
    rms_db: float = 0.0
    peak_db: float = 0.0
    noise_db: float = 0.0
    snr_db: float = 0.0
    
    # DSP处理
    dsp_needed: bool = False
    dsp_algorithm: str = ""
    dsp_applied: bool = False
    processed_snr_db: float = 0.0
    
    # 识别结果
    signal_type: str = ""  # CQ, QSO, NOISE, UNKNOWN
    content: str = ""
    content_normalized: str = ""
    confidence: float = 0.0
    
    # 元数据
    duration: float = 0.0
    audio_path: str = ""


@dataclass
class Recording:
    """录音记录"""
    id: Optional[int] = None
    filepath: str = ""
    filename: str = ""
    channel_id: int = 0
    user_id: str = ""          # 用户ID (SSRC)
    user_name: str = ""        # 用户昵称
    recorder_type: str = ""    # RX/TX
    duration: float = 0.0      # 录音时长(秒)，精确到0.1
    start_time: str = ""        # 开始录音时间，精确到0.1秒 (如: 2026-02-18 13:41:37.9)
    file_size: int = 0         # 文件大小(bytes)
    timestamp: str = ""        # 录音时间戳
    
    # 识别状态
    recognized: bool = False    # 是否已识别
    asr_text: str = ""         # ASR识别文本
    content_normalized: str = "" # 规范化后的文本
    signal_type: str = ""      # 信号类型
    confidence: float = 0.0     # 置信度
    
    # 音频质量
    rms_db: float = 0.0
    snr_db: float = 0.0


class Database:
    """SQLite数据库管理"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = "data/records.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = "data/records.db"):
        if self._initialized:
            return
        
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()
        self._initialized = True
    
    def _ensure_dir(self):
        """确保数据库目录存在"""
        dir_path = os.path.dirname(self.db_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                nickname TEXT,
                
                -- 音频质量
                rms_db REAL,
                peak_db REAL,
                noise_db REAL,
                snr_db REAL,
                
                -- DSP处理
                dsp_needed INTEGER,
                dsp_algorithm TEXT,
                dsp_applied INTEGER,
                processed_snr_db REAL,
                
                -- 识别结果
                signal_type TEXT,
                content TEXT,
                content_normalized TEXT,
                confidence REAL,
                
                -- 元数据
                duration REAL,
                audio_path TEXT
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON audio_records(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_user ON audio_records(channel_id, user_id)
        """)
        
        # 录音记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT NOT NULL,
                filename TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id TEXT,
                user_name TEXT,
                recorder_type TEXT,
                duration REAL,
                start_time TEXT,
                file_size INTEGER,
                timestamp TEXT NOT NULL,
                
                -- 识别状态
                recognized INTEGER DEFAULT 0,
                asr_text TEXT,
                content_normalized TEXT,
                signal_type TEXT,
                confidence REAL,
                
                -- 音频质量
                rms_db REAL,
                snr_db REAL
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rec_timestamp ON recordings(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rec_recognized ON recordings(recognized)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rec_channel ON recordings(channel_id, recorder_type)
        """)
        
        conn.commit()
        conn.close()
    
    def add_record(self, record: AudioRecord) -> int:
        """添加识别记录"""
        if not record.timestamp:
            record.timestamp = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audio_records (
                timestamp, channel_id, user_id, nickname,
                rms_db, peak_db, noise_db, snr_db,
                dsp_needed, dsp_algorithm, dsp_applied, processed_snr_db,
                signal_type, content, content_normalized, confidence,
                duration, audio_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.timestamp,
            record.channel_id,
            record.user_id,
            record.nickname,
            record.rms_db,
            record.peak_db,
            record.noise_db,
            record.snr_db,
            1 if record.dsp_needed else 0,
            record.dsp_algorithm,
            1 if record.dsp_applied else 0,
            record.processed_snr_db,
            record.signal_type,
            record.content,
            record.content_normalized,
            record.confidence,
            record.duration,
            record.audio_path
        ))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return record_id
    
    def get_records(self, 
                   channel_id: Optional[int] = None,
                   user_id: Optional[int] = None,
                   limit: int = 100,
                   offset: int = 0) -> List[AudioRecord]:
        """查询识别记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM audio_records WHERE 1=1"
        params = []
        
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            record = AudioRecord(
                id=row[0],
                timestamp=row[1],
                channel_id=row[2],
                user_id=row[3],
                nickname=row[4],
                rms_db=row[5],
                peak_db=row[6],
                noise_db=row[7],
                snr_db=row[8],
                dsp_needed=bool(row[9]),
                dsp_algorithm=row[10],
                dsp_applied=bool(row[11]),
                processed_snr_db=row[12],
                signal_type=row[13],
                content=row[14],
                content_normalized=row[15],
                confidence=row[16],
                duration=row[17],
                audio_path=row[18]
            )
            records.append(record)
        
        return records
    
    def get_record_by_id(self, record_id: int) -> Optional[AudioRecord]:
        """根据ID查询记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM audio_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return AudioRecord(
            id=row[0],
            timestamp=row[1],
            channel_id=row[2],
            user_id=row[3],
            nickname=row[4],
            rms_db=row[5],
            peak_db=row[6],
            noise_db=row[7],
            snr_db=row[8],
            dsp_needed=bool(row[9]),
            dsp_algorithm=row[10],
            dsp_applied=bool(row[11]),
            processed_snr_db=row[12],
            signal_type=row[13],
            content=row[14],
            content_normalized=row[15],
            confidence=row[16],
            duration=row[17],
            audio_path=row[18]
        )
    
    def delete_old_records(self, keep_count: int = 10000) -> int:
        """删除旧记录，保留最新的一定数量"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM audio_records")
        total = cursor.fetchone()[0]
        
        if total > keep_count:
            delete_count = total - keep_count
            cursor.execute("""
                DELETE FROM audio_records 
                WHERE id IN (
                    SELECT id FROM audio_records 
                    ORDER BY timestamp ASC 
                    LIMIT ?
                )
            """, (delete_count,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            return deleted
        
        conn.close()
        return 0
    
    def get_statistics(self, channel_id: Optional[int] = None) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        where = f"WHERE channel_id = {channel_id}" if channel_id else ""
        
        # 总数
        cursor.execute(f"SELECT COUNT(*) FROM audio_records {where}")
        total = cursor.fetchone()[0]
        
        # DSP处理统计
        cursor.execute(f"SELECT COUNT(*) FROM audio_records {where and where + ' AND' or 'WHERE'} dsp_needed = 1")
        dsp_needed = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(*) FROM audio_records {where and where + ' AND' or 'WHERE'} dsp_applied = 1")
        dsp_applied = cursor.fetchone()[0]
        
        # 信号类型统计
        cursor.execute(f"""
            SELECT signal_type, COUNT(*) as cnt 
            FROM audio_records {where} 
            GROUP BY signal_type
        """)
        signal_types = dict(cursor.fetchall())
        
        # 平均置信度
        cursor.execute(f"SELECT AVG(confidence) FROM audio_records {where and where + ' AND' or 'WHERE'} confidence > 0")
        avg_confidence = cursor.fetchone()[0] or 0.0
        
        conn.close()
        
        return {
            "total": total,
            "dsp_needed": dsp_needed,
            "dsp_applied": dsp_applied,
            "signal_types": signal_types,
            "avg_confidence": avg_confidence
        }
    
    # ========== Recording 相关方法 ==========
    
    def add_recording(self, recording: Recording) -> int:
        """添加录音记录"""
        if not recording.timestamp:
            recording.timestamp = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO recordings (
                filepath, filename, channel_id, user_id, user_name,
                recorder_type, duration, start_time, file_size, timestamp,
                recognized, asr_text, content_normalized, signal_type, confidence,
                rms_db, snr_db
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            recording.filepath,
            recording.filename,
            recording.channel_id,
            recording.user_id,
            recording.user_name,
            recording.recorder_type,
            recording.duration,
            recording.start_time,
            recording.file_size,
            recording.timestamp,
            1 if recording.recognized else 0,
            recording.asr_text,
            recording.content_normalized,
            recording.signal_type,
            recording.confidence,
            recording.rms_db,
            recording.snr_db
        ))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return record_id
    
    def update_recording_recognition(self, filepath: str, 
                                     asr_text: str = "", 
                                     content_normalized: str = "",
                                     signal_type: str = "",
                                     confidence: float = 0.0,
                                     rms_db: float = 0.0,
                                     snr_db: float = 0.0) -> bool:
        """更新录音的识别结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE recordings 
            SET recognized = 1, asr_text = ?, content_normalized = ?, signal_type = ?, 
                confidence = ?, rms_db = ?, snr_db = ?
            WHERE filepath = ?
        """, (asr_text, content_normalized, signal_type, confidence, rms_db, snr_db, filepath))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def get_recordings(self, 
                       channel_id: Optional[int] = None,
                       recorder_type: Optional[str] = None,
                       recognized: Optional[bool] = None,
                       limit: int = 100,
                       offset: int = 0) -> List[Recording]:
        """查询录音记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM recordings WHERE 1=1"
        params = []
        
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        
        if recorder_type:
            query += " AND recorder_type = ?"
            params.append(recorder_type)
        
        if recognized is not None:
            query += " AND recognized = ?"
            params.append(1 if recognized else 0)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        recordings = []
        for row in rows:
            recording = Recording(
                id=row[0],
                filepath=row[1],
                filename=row[2],
                channel_id=row[3],
                user_id=row[4] or "",
                user_name=row[5] or "",
                recorder_type=row[6] or "",
                duration=row[7] or 0.0,
                start_time=row[8] or "",
                file_size=row[9] or 0,
                timestamp=row[10],
                recognized=bool(row[11]),
                asr_text=row[12] or "",
                content_normalized=row[13] or "",
                signal_type=row[14] or "",
                confidence=row[15] or 0.0,
                rms_db=row[16] or 0.0,
                snr_db=row[17] or 0.0
            )
            recordings.append(recording)
        
        return recordings
    
    def get_unrecognized_recordings(self, limit: int = 10) -> List[Recording]:
        """获取未识别的录音"""
        return self.get_recordings(recognized=False, limit=limit)
    
    def get_recording_by_path(self, filepath: str) -> Optional[Recording]:
        """根据路径查询录音"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM recordings WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Recording(
            id=row[0],
            filepath=row[1],
            filename=row[2],
            channel_id=row[3],
            user_id=row[4] or "",
            user_name=row[5] or "",
            recorder_type=row[6] or "",
            duration=row[7] or 0.0,
            start_time=row[8] or "",
            file_size=row[9] or 0,
            timestamp=row[10],
            recognized=bool(row[11]),
            asr_text=row[12] or "",
            content_normalized=row[13] or "",
            signal_type=row[14] or "",
            confidence=row[15] or 0.0,
            rms_db=row[16] or 0.0,
            snr_db=row[17] or 0.0
        )
    
    def close(self):
        """关闭数据库连接"""
        pass  # SQLite自动管理连接


# 全局数据库实例
_db: Optional[Database] = None


def get_database(db_path: str = "data/records.db") -> Database:
    """获取全局数据库实例"""
    global _db
    if _db is None:
        _db = Database(db_path)
    return _db
