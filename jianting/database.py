# database.py
import sqlite3
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import List, Optional, Generic, TypeVar
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class Channel:
    id: Optional[int] = None
    channel_id: int = 0
    name: str = ""
    passcode: int = 0
    auto_join: bool = False
    auto_record: bool = True
    created_at: Optional[datetime] = None


@dataclass
class Recording:
    id: Optional[int] = None
    channel_id: int = 0
    file_path: str = ""
    speaker_id: Optional[int] = None
    speaker_name: str = "Unknown"
    start_time: Optional[datetime] = None
    duration_sec: float = 0.0
    frames: int = 0
    lost_frames: int = 0
    loss_rate: float = 0.0
    transcription: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Message:
    id: Optional[int] = None
    channel_id: int = 0
    user_id: int = 0
    username: str = ""
    content: str = ""
    msg_type: str = "text"
    created_at: Optional[datetime] = None


class Repository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> int:
        pass

    @abstractmethod
    def get_by_id(self, id: int) -> Optional[T]:
        pass

    @abstractmethod
    def list(self, limit: int = 100, offset: int = 0) -> List[T]:
        pass

    @abstractmethod
    def update(self, id: int, **kwargs) -> bool:
        pass

    @abstractmethod
    def delete(self, id: int) -> bool:
        pass


class Database:
    _instance = None
    _conn: sqlite3.Connection = None

    def __new__(cls, db_path: str = "audio.db"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "audio.db"):
        if self._conn is None:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL UNIQUE,
                name TEXT,
                passcode INTEGER DEFAULT 0,
                auto_join BOOLEAN DEFAULT 0,
                auto_record BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                speaker_id INTEGER,
                speaker_name TEXT,
                start_time TIMESTAMP NOT NULL,
                duration_sec REAL,
                frames INTEGER,
                lost_frames INTEGER DEFAULT 0,
                loss_rate REAL DEFAULT 0,
                transcription TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );

            CREATE INDEX IF NOT EXISTS idx_channel_time
                ON recordings(channel_id, start_time DESC);

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                content TEXT NOT NULL,
                msg_type TEXT DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );

            CREATE INDEX IF NOT EXISTS idx_channel_msg_time
                ON messages(channel_id, created_at DESC);
        """)
        self._conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn


class ChannelRepository(Repository[Channel]):
    def __init__(self, db: Database):
        self._db = db

    def add(self, entity: Channel) -> int:
        cursor = self._db.connection.execute(
            "INSERT INTO channels (channel_id, name, passcode, auto_join, auto_record) VALUES (?, ?, ?, ?, ?)",
            (entity.channel_id, entity.name, entity.passcode, entity.auto_join, entity.auto_record)
        )
        self._db.connection.commit()
        return cursor.lastrowid

    def get_by_id(self, id: int) -> Optional[Channel]:
        row = self._db.connection.execute("SELECT * FROM channels WHERE id = ?", (id,)).fetchone()
        return Channel(**dict(row)) if row else None

    def list(self, limit: int = 100, offset: int = 0) -> List[Channel]:
        rows = self._db.connection.execute(
            "SELECT * FROM channels LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [Channel(**dict(row)) for row in rows]

    def list_by_auto_join(self, auto_join: bool) -> List[Channel]:
        rows = self._db.connection.execute(
            "SELECT * FROM channels WHERE auto_join = ?", (1 if auto_join else 0,)
        ).fetchall()
        return [Channel(**dict(row)) for row in rows]

    def list_all(self) -> List[Channel]:
        rows = self._db.connection.execute("SELECT * FROM channels").fetchall()
        return [Channel(**dict(row)) for row in rows]

    def update(self, id: int, **kwargs) -> bool:
        pass

    def delete(self, id: int) -> bool:
        cursor = self._db.connection.execute("DELETE FROM channels WHERE id = ?", (id,))
        self._db.connection.commit()
        return cursor.rowcount > 0


class RecordingRepository(Repository[Recording]):
    def __init__(self, db: Database):
        self._db = db

    def add(self, entity: Recording) -> int:
        cursor = self._db.connection.execute(
            """INSERT INTO recordings
               (channel_id, file_path, speaker_id, speaker_name, start_time,
                duration_sec, frames, lost_frames, loss_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity.channel_id, entity.file_path, entity.speaker_id,
             entity.speaker_name, entity.start_time, entity.duration_sec,
             entity.frames, entity.lost_frames, entity.loss_rate)
        )
        self._db.connection.commit()
        return cursor.lastrowid

    def get_by_id(self, id: int) -> Optional[Recording]:
        row = self._db.connection.execute("SELECT * FROM recordings WHERE id = ?", (id,)).fetchone()
        return Recording(**dict(row)) if row else None

    def list(self, limit: int = 100, offset: int = 0) -> List[Recording]:
        rows = self._db.connection.execute(
            "SELECT * FROM recordings ORDER BY start_time DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [Recording(**dict(row)) for row in rows]

    def list_by_channel(self, channel_id: int, limit: int = 100) -> List[Recording]:
        rows = self._db.connection.execute(
            "SELECT * FROM recordings WHERE channel_id = ? ORDER BY start_time DESC LIMIT ?",
            (channel_id, limit)
        ).fetchall()
        return [Recording(**dict(row)) for row in rows]

    def update(self, id: int, **kwargs) -> bool:
        pass

    def delete(self, id: int) -> bool:
        cursor = self._db.connection.execute("DELETE FROM recordings WHERE id = ?", (id,))
        self._db.connection.commit()
        return cursor.rowcount > 0
