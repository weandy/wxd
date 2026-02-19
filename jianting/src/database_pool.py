"""
SQLite 连接池实现

提供线程安全的数据库连接池，解决多线程并发访问的性能问题
"""

import sqlite3
import threading
import queue
import logging
import atexit
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite 连接池

    特性:
    - 线程安全的连接池
    - 自动重连
    - 连接健康检查
    - 上下文管理器支持
    - 性能优化 (WAL模式, 缓存等)

    Usage:
        pool = DatabaseConnectionPool("data/records.db", pool_size=5)

        with pool.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM recordings")
            results = cursor.fetchall()

        # 或者
        def update_data():
            with pool.get_connection() as conn:
                conn.execute("UPDATE recordings SET recognized=1")
    """

    def __init__(self,
                 db_path: str,
                 pool_size: int = 5,
                 max_overflow: int = 10,
                 timeout: float = 30.0):
        """
        初始化连接池

        Args:
            db_path: 数据库文件路径
            pool_size: 基础连接池大小
            max_overflow: 最大额外连接数
            timeout: 获取连接超时时间(秒)
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout

        # 连接队列
        max_size = pool_size + max_overflow
        self._pool = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._created_connections = 0

        # 统计信息
        self._stats = {
            'created': 0,
            'reused': 0,
            'closed': 0,
            'errors': 0,
            'timeouts': 0
        }

        # 预创建连接
        self._initialize_pool()

        logger.info(
            f"连接池初始化完成: {db_path}, "
            f"大小={pool_size}, 溢出={max_overflow}"
        )

    def _initialize_pool(self):
        """预创建连接"""
        created = 0
        for _ in range(self.pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
                created += 1

        logger.debug(f"预创建 {created} 个连接")

    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """创建新连接"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许跨线程
                timeout=self.timeout,
                isolation_level=None  # 自动提交模式
            )

            # 性能优化
            self._optimize_connection(conn)

            # 设置行工厂
            conn.row_factory = sqlite3.Row

            with self._lock:
                self._created_connections += 1
                self._stats['created'] += 1

            logger.debug(f"创建新连接: 总数={self._created_connections}")
            return conn

        except Exception as e:
            logger.error(f"创建连接失败: {e}")
            self._stats['errors'] += 1
            return None

    def _optimize_connection(self, conn: sqlite3.Connection):
        """优化连接性能"""
        # 启用WAL模式 (Write-Ahead Logging)
        # 允许读写并发，大幅提升多线程性能
        conn.execute("PRAGMA journal_mode=WAL")

        # 平衡模式 (安全性和性能的平衡)
        conn.execute("PRAGMA synchronous=NORMAL")

        # 增大缓存 (64MB)
        conn.execute("PRAGMA cache_size=-64000")

        # 临时表在内存中
        conn.execute("PRAGMA temp_store=MEMORY")

        # 忙碌超时 (毫秒)
        conn.execute("PRAGMA busy_timeout=30000")

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """验证连接是否可用"""
        try:
            # 执行简单查询测试连接
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    @contextmanager
    def get_connection(self):
        """
        获取连接 (上下文管理器)

        用法:
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT ...")
                results = cursor.fetchall()

        Yields:
            sqlite3.Connection: 数据库连接
        """
        conn = None
        try:
            # 尝试从池中获取连接
            try:
                conn = self._pool.get(timeout=self.timeout)

                # 健康检查
                if not self._validate_connection(conn):
                    logger.warning("连接不可用，创建新连接")
                    conn.close()
                    conn = self._create_connection()

                self._stats['reused'] += 1

            except queue.Empty:
                # 池已空，创建新连接 (溢出)
                logger.warning("连接池已空，创建溢出连接")
                conn = self._create_connection()
                self._stats['timeouts'] += 1

            if conn is None:
                raise TimeoutError("获取数据库连接超时")

            yield conn

        finally:
            # 归还连接到池
            if conn:
                try:
                    self._pool.put(conn, block=False)
                except queue.Full:
                    # 池已满，关闭连接
                    logger.debug("连接池已满，关闭溢出连接")
                    try:
                        conn.close()
                        self._stats['closed'] += 1
                    except Exception:
                        pass

    def execute_safe(self, query: str, params: tuple = ()):
        """
        安全执行查询 (自动管理连接)

        Args:
            query: SQL查询语句
            params: 查询参数

        Returns:
            sqlite3.Cursor: 游标对象
        """
        with self.get_connection() as conn:
            return conn.execute(query, params)

    def executemany_safe(self, query: str, params_list: list):
        """
        批量执行查询 (自动管理连接)

        Args:
            query: SQL查询语句
            params_list: 参数列表

        Returns:
            sqlite3.Cursor: 游标对象
        """
        with self.get_connection() as conn:
            return conn.executemany(query, params_list)

    def close_all(self):
        """关闭所有连接"""
        logger.info("关闭所有连接...")

        closed_count = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                self._stats['closed'] += 1
                closed_count += 1
            except queue.Empty:
                break

        logger.info(
            f"连接池已关闭: 关闭 {closed_count} 个连接, "
            f"统计={self._stats}"
        )

    def get_stats(self) -> dict:
        """
        获取连接池统计信息

        Returns:
            dict: 统计信息字典
        """
        return {
            **self._stats,
            'pool_size': self._created_connections,
            'available': self._pool.qsize(),
            'waiting': 0,  # Python 3.10+ 不再暴露此属性
            'utilization': f"{(self._stats['reused'] / max(self._stats['created'], 1) * 100):.1f}%"
        }

    def __del__(self):
        """析构函数"""
        try:
            self.close_all()
        except Exception:
            pass


# 全局连接池实例
_global_pool: Optional[DatabaseConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool(db_path: str = "data/records.db",
                       pool_size: int = 5) -> DatabaseConnectionPool:
    """
    获取全局连接池实例 (单例模式)

    Args:
        db_path: 数据库文件路径
        pool_size: 连接池大小

    Returns:
        DatabaseConnectionPool: 连接池实例
    """
    global _global_pool

    with _pool_lock:
        if _global_pool is None:
            _global_pool = DatabaseConnectionPool(db_path, pool_size)
            logger.info(f"创建全局连接池: {db_path}")

        return _global_pool


def close_global_pool():
    """关闭全局连接池"""
    global _global_pool

    if _global_pool:
        _global_pool.close_all()
        _global_pool = None


# 程序退出时自动清理
atexit.register(close_global_pool)
