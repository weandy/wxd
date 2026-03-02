"""
数据库模块 - SQLite存储音频识别结果
高内聚低耦合设计

异步支持:
    要使用异步数据库操作，可以导入 async_database_wrapper:
    from async_database_wrapper import get_async_database
    async_db = get_async_database(get_database())
    await async_db.add_recording(recording)
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

    # 识别耗时
    recognize_duration: float = 0.0  # 识别耗时(秒)

    # 无效音频标记
    invalid_reason: str = ""  # 无效原因 (empty=有效, "duration_too_short"=时长不足等)


@dataclass
class User:
    """用户账户"""
    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    nickname: str = ""
    role: str = "user"  # admin / user
    created_at: str = ""
    last_login: str = ""
    is_active: bool = True


@dataclass
class CorrectionRule:
    """纠错规则"""
    id: Optional[int] = None
    name: str = ""
    rule_type: str = ""  # replace / preserve / regex
    pattern: str = ""
    replacement: str = ""
    description: str = ""
    category: str = ""  # must_replace / preserve / custom
    priority: int = 0
    is_enabled: bool = True
    created_by: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class BroadcastTask:
    """广播任务"""
    id: Optional[int] = None
    name: str = ""
    task_type: str = ""  # scheduled / event_triggered
    trigger_type: str = ""  # hourly / daily / user_join
    trigger_config: str = ""  # JSON
    content_type: str = ""  # tts / audio_file
    audio_file_id: Optional[int] = None
    tts_text: str = ""
    tts_config: str = ""  # JSON
    is_enabled: bool = True
    last_executed: str = ""
    execution_count: int = 0
    created_by: int = 0
    created_at: str = ""


@dataclass
class AudioLibrary:
    """音频库"""
    id: Optional[int] = None
    filename: str = ""
    filepath: str = ""
    source_type: str = ""  # tts / upload / record
    description: str = ""
    duration: float = 0.0
    file_size: int = 0
    metadata: str = ""  # JSON
    created_by: int = 0
    created_at: str = ""


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
                filepath TEXT NOT NULL UNIQUE,
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
                snr_db REAL,

                -- 识别耗时
                recognize_duration REAL,

                -- 无效音频标记
                invalid_reason TEXT DEFAULT ''
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
        
        # 数据库迁移：添加invalid_reason字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE recordings ADD COLUMN invalid_reason TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 字段可能已存在

        # 数据库迁移：添加recorder_type字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE recordings ADD COLUMN recorder_type TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 字段可能已存在

        # 数据库迁移：添加user_name字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE recordings ADD COLUMN user_name TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 字段可能已存在

        # 数据库迁移：添加filepath唯一约束（如果不存在）
        # SQLite 不支持直接添加 UNIQUE 约束到已存在的表
        # 需要重建表，这里我们只添加索引来提高查询性能
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_recording_filepath
                ON recordings(filepath)
            """)
        except sqlite3.OperationalError:
            pass  # 索引可能已存在

        # 微信推送服务表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notify_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                url TEXT,
                token TEXT,
                config TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 推送目标用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notify_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                user_identifier TEXT NOT NULL,
                keywords TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_id) REFERENCES notify_services(id)
            )
        """)

        # ===== Web 平台新增表 =====

        # 用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                nickname TEXT,
                role TEXT DEFAULT 'user',
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 纠错规则表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correction_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                replacement TEXT,
                description TEXT,
                category TEXT,
                priority INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)

        # 广播任务表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                trigger_type TEXT,
                trigger_config TEXT,
                content_type TEXT NOT NULL,
                audio_file_id INTEGER,
                tts_text TEXT,
                tts_config TEXT,
                is_enabled INTEGER DEFAULT 1,
                last_executed TEXT,
                execution_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (audio_file_id) REFERENCES audio_library(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)

        # 音频库表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                description TEXT,
                duration REAL,
                file_size INTEGER,
                metadata TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rules_enabled ON correction_rules(is_enabled)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rules_category ON correction_rules(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_enabled ON broadcast_tasks(is_enabled)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audio_source ON audio_library(source_type)
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
        """添加录音记录 - 如果 filepath 已存在则更新"""
        if not recording.timestamp:
            recording.timestamp = datetime.now().isoformat()

        # 标准化路径
        import os
        recording.filepath = os.path.normpath(recording.filepath)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT id FROM recordings WHERE filepath = ?", (recording.filepath,))
        existing = cursor.fetchone()

        if existing:
            # 更新现有记录
            record_id = existing[0]
            cursor.execute("""
                UPDATE recordings SET
                    filename = ?, channel_id = ?, user_id = ?, user_name = ?,
                    recorder_type = ?, duration = ?, start_time = ?, file_size = ?,
                    timestamp = ?, recognized = ?, asr_text = ?, content_normalized = ?,
                    signal_type = ?, confidence = ?, rms_db = ?, snr_db = ?,
                    invalid_reason = COALESCE(?, invalid_reason)
                WHERE id = ?
            """, (
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
                recording.snr_db,
                recording.invalid_reason,
                record_id
            ))
        else:
            # 插入新记录
            cursor.execute("""
                INSERT INTO recordings (
                    filepath, filename, channel_id, user_id, user_name,
                    recorder_type, duration, start_time, file_size, timestamp,
                    recognized, asr_text, content_normalized, signal_type, confidence,
                    rms_db, snr_db, invalid_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                recording.snr_db,
                recording.invalid_reason
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
                                     snr_db: float = 0.0,
                                     recognize_duration: float = 0.0,
                                     invalid_reason: str = "") -> bool:
        """更新录音的识别结果"""
        import os
        filepath = os.path.normpath(filepath)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE recordings
            SET recognized = 1, asr_text = ?, content_normalized = ?, signal_type = ?,
                confidence = ?, rms_db = ?, snr_db = ?, recognize_duration = ?, invalid_reason = ?
            WHERE filepath = ?
        """, (asr_text, content_normalized, signal_type, confidence, rms_db, snr_db, recognize_duration, invalid_reason, filepath))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0
    
    def get_recordings(self,
                       channel_id: Optional[int] = None,
                       recorder_type: Optional[str] = None,
                       recognized: Optional[bool] = None,
                       user_id: Optional[str] = None,
                       search: Optional[str] = None,
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

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if search:
            # 搜索识别文本或归一化文本
            query += " AND (asr_text LIKE ? OR content_normalized LIKE ?)"
            search_pattern = f"%{search}%"
            params.append(search_pattern)
            params.append(search_pattern)
        
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
                snr_db=row[17] or 0.0,
                recognize_duration=row[18] or 0.0 if len(row) > 18 else 0.0
            )
            recordings.append(recording)
        
        return recordings
    
    def get_unrecognized_recordings(self, limit: int = 10) -> List[Recording]:
        """获取未识别的录音"""
        return self.get_recordings(recognized=False, limit=limit)
    
    def get_recording_by_path(self, filepath: str) -> Optional[Recording]:
        """根据路径查询录音"""
        import os
        filepath = os.path.normpath(filepath)

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
            snr_db=row[17] or 0.0,
            recognize_duration=row[18] or 0.0 if len(row) > 18 else 0.0
        )

    # ===== Web 平台新增方法 =====

    # --- 用户管理 ---

    def create_user(self, user: User) -> int:
        """创建用户"""
        if not user.created_at:
            user.created_at = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (username, password_hash, nickname, role, created_at, last_login, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user.username,
            user.password_hash,
            user.nickname,
            user.role,
            user.created_at,
            user.last_login,
            1 if user.is_active else 0
        ))

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return user_id

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            nickname=row[3] or "",
            role=row[4],
            created_at=row[5],
            last_login=row[6] or "",
            is_active=bool(row[7])
        )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据 ID 获取用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            nickname=row[3] or "",
            role=row[4],
            created_at=row[5],
            last_login=row[6] or "",
            is_active=bool(row[7])
        )

    def update_user_login(self, user_id: int):
        """更新用户登录时间"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users SET last_login = ? WHERE id = ?
        """, (datetime.now().isoformat(), user_id))

        conn.commit()
        conn.close()

    def get_all_users(self) -> List[User]:
        """获取所有用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        users = []
        for row in rows:
            users.append(User(
                id=row[0],
                username=row[1],
                password_hash=row[2],
                nickname=row[3] or "",
                role=row[4],
                created_at=row[5],
                last_login=row[6] or "",
                is_active=bool(row[7])
            ))

        return users

    # --- 纠错规则管理 ---

    def create_rule(self, rule: CorrectionRule) -> int:
        """创建纠错规则"""
        if not rule.created_at:
            rule.created_at = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO correction_rules
            (name, rule_type, pattern, replacement, description, category, priority, is_enabled, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.name,
            rule.rule_type,
            rule.pattern,
            rule.replacement,
            rule.description,
            rule.category,
            rule.priority,
            1 if rule.is_enabled else 0,
            rule.created_by,
            rule.created_at,
            rule.updated_at
        ))

        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return rule_id

    def get_rules(self, category: Optional[str] = None, enabled_only: bool = False) -> List[CorrectionRule]:
        """获取纠错规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM correction_rules WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if enabled_only:
            query += " AND is_enabled = 1"
            params.append(1)

        query += " ORDER BY priority DESC, id ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        rules = []
        for row in rows:
            rules.append(CorrectionRule(
                id=row[0],
                name=row[1],
                rule_type=row[2],
                pattern=row[3],
                replacement=row[4] or "",
                description=row[5] or "",
                category=row[6] or "",
                priority=row[7],
                is_enabled=bool(row[8]),
                created_by=row[9],
                created_at=row[10],
                updated_at=row[11] or ""
            ))

        return rules

    def update_rule(self, rule_id: int, rule: CorrectionRule):
        """更新纠错规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE correction_rules
            SET name = ?, rule_type = ?, pattern = ?, replacement = ?,
                description = ?, category = ?, priority = ?, is_enabled = ?, updated_at = ?
            WHERE id = ?
        """, (
            rule.name,
            rule.rule_type,
            rule.pattern,
            rule.replacement,
            rule.description,
            rule.category,
            rule.priority,
            1 if rule.is_enabled else 0,
            datetime.now().isoformat(),
            rule_id
        ))

        conn.commit()
        conn.close()

    def delete_rule(self, rule_id: int):
        """删除纠错规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM correction_rules WHERE id = ?", (rule_id,))

        conn.commit()
        conn.close()

    def get_rule_by_id(self, rule_id: int) -> Optional[CorrectionRule]:
        """根据 ID 获取规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM correction_rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return CorrectionRule(
            id=row[0],
            name=row[1],
            rule_type=row[2],
            pattern=row[3],
            replacement=row[4] or "",
            description=row[5] or "",
            category=row[6] or "",
            priority=row[7],
            is_enabled=bool(row[8]),
            created_by=row[9],
            created_at=row[10],
            updated_at=row[11] or ""
        )

    # --- 音频库管理 ---

    def create_audio(self, audio: AudioLibrary) -> int:
        """添加音频到库"""
        if not audio.created_at:
            audio.created_at = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audio_library
            (filename, filepath, source_type, description, duration, file_size, metadata, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audio.filename,
            audio.filepath,
            audio.source_type,
            audio.description,
            audio.duration,
            audio.file_size,
            audio.metadata,
            audio.created_by,
            audio.created_at
        ))

        audio_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return audio_id

    def get_audio_list(self, source_type: Optional[str] = None) -> List[AudioLibrary]:
        """获取音频列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM audio_library WHERE 1=1"
        params = []

        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        audio_list = []
        for row in rows:
            audio_list.append(AudioLibrary(
                id=row[0],
                filename=row[1],
                filepath=row[2],
                source_type=row[3],
                description=row[4] or "",
                duration=row[5] or 0.0,
                file_size=row[6] or 0,
                metadata=row[7] or "",
                created_by=row[8],
                created_at=row[9]
            ))

        return audio_list

    def get_audio_by_id(self, audio_id: int) -> Optional[AudioLibrary]:
        """根据 ID 获取音频"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM audio_library WHERE id = ?", (audio_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AudioLibrary(
            id=row[0],
            filename=row[1],
            filepath=row[2],
            source_type=row[3],
            description=row[4] or "",
            duration=row[5] or 0.0,
            file_size=row[6] or 0,
            metadata=row[7] or "",
            created_by=row[8],
            created_at=row[9]
        )

    def delete_audio(self, audio_id: int):
        """删除音频"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM audio_library WHERE id = ?", (audio_id,))

        conn.commit()
        conn.close()

    # --- 广播任务管理 ---

    def create_broadcast_task(self, task: BroadcastTask) -> int:
        """创建广播任务"""
        if not task.created_at:
            task.created_at = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO broadcast_tasks
            (name, task_type, trigger_type, trigger_config, content_type, audio_file_id, tts_text, tts_config, is_enabled, last_executed, execution_count, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.name,
            task.task_type,
            task.trigger_type,
            task.trigger_config,
            task.content_type,
            task.audio_file_id,
            task.tts_text,
            task.tts_config,
            1 if task.is_enabled else 0,
            task.last_executed,
            task.execution_count,
            task.created_by,
            task.created_at
        ))

        task_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return task_id

    def get_broadcast_tasks(self, enabled_only: bool = False) -> List[BroadcastTask]:
        """获取广播任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM broadcast_tasks WHERE 1=1"
        params = []

        if enabled_only:
            query += " AND is_enabled = 1"
            params.append(1)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            tasks.append(BroadcastTask(
                id=row[0],
                name=row[1],
                task_type=row[2],
                trigger_type=row[3] or "",
                trigger_config=row[4] or "",
                content_type=row[5],
                audio_file_id=row[6],
                tts_text=row[7] or "",
                tts_config=row[8] or "",
                is_enabled=bool(row[9]),
                last_executed=row[10] or "",
                execution_count=row[11],
                created_by=row[12],
                created_at=row[13]
            ))

        return tasks

    def get_broadcast_task_by_id(self, task_id: int) -> Optional[BroadcastTask]:
        """根据 ID 获取广播任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM broadcast_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return BroadcastTask(
            id=row[0],
            name=row[1],
            task_type=row[2],
            trigger_type=row[3] or "",
            trigger_config=row[4] or "",
            content_type=row[5],
            audio_file_id=row[6],
            tts_text=row[7] or "",
            tts_config=row[8] or "",
            is_enabled=bool(row[9]),
            last_executed=row[10] or "",
            execution_count=row[11],
            created_by=row[12],
            created_at=row[13]
        )

    def update_broadcast_task(self, task_id: int, task: BroadcastTask):
        """更新广播任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE broadcast_tasks
            SET name = ?, task_type = ?, trigger_type = ?, trigger_config = ?,
                content_type = ?, audio_file_id = ?, tts_text = ?, tts_config = ?,
                is_enabled = ?
            WHERE id = ?
        """, (
            task.name,
            task.task_type,
            task.trigger_type,
            task.trigger_config,
            task.content_type,
            task.audio_file_id,
            task.tts_text,
            task.tts_config,
            1 if task.is_enabled else 0,
            task_id
        ))

        conn.commit()
        conn.close()

    def delete_broadcast_task(self, task_id: int):
        """删除广播任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM broadcast_tasks WHERE id = ?", (task_id,))

        conn.commit()
        conn.close()

    def update_task_execution(self, task_id: int):
        """更新任务执行记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE broadcast_tasks
            SET last_executed = ?, execution_count = execution_count + 1
            WHERE id = ?
        """, (datetime.now().isoformat(), task_id))

        conn.commit()
        conn.close()

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
