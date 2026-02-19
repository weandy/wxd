"""
安全的数据库查询工具

防止SQL注入，提供输入验证和安全查询方法
"""

import os
import re
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityValidator:
    """安全验证器"""

    # 危险的SQL关键词
    DANGEROUS_SQL_KEYWORDS = [
        'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
        'EXEC', 'EXECUTE', 'SCRIPT', 'GRANT', 'REVOKE',
        'INSERT', 'UPDATE', '--', '/*', '*/', ';'
    ]

    @staticmethod
    def validate_sql(query: str) -> bool:
        """
        验证SQL语句安全性

        Args:
            query: SQL查询语句

        Returns:
            bool: 是否安全

        Raises:
            ValueError: 如果SQL包含危险操作
        """
        if not query or not isinstance(query, str):
            raise ValueError("SQL查询不能为空")

        query_upper = query.upper()

        # 检查危险关键词
        for keyword in SecurityValidator.DANGEROUS_SQL_KEYWORDS:
            if keyword in query_upper:
                error_msg = f"SQL查询包含危险操作: {keyword}"
                logger.error(f"{error_msg} - {query[:100]}")
                raise ValueError(error_msg)

        return True

    @staticmethod
    def validate_filepath(filepath: str) -> bool:
        """
        验证文件路径安全性 (防止路径遍历攻击)

        Args:
            filepath: 文件路径

        Returns:
            bool: 是否安全

        Raises:
            ValueError: 如果路径不安全
        """
        if not filepath or not isinstance(filepath, str):
            raise ValueError("文件路径不能为空")

        # 规范化路径
        normalized = os.path.normpath(filepath)

        # 检查路径遍历攻击
        if '..' in normalized:
            error_msg = f"检测到路径遍历尝试: {filepath}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 检查绝对路径攻击
        if os.path.isabs(normalized):
            # 只允许特定目录的绝对路径
            allowed_roots = os.path.abspath('recordings')
            if not normalized.startswith(allowed_roots):
                error_msg = f"文件路径不在允许目录下: {filepath}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        return True

    @staticmethod
    def validate_user_input(value: str,
                           max_length: int = 255,
                           allow_empty: bool = False) -> bool:
        """
        验证用户输入

        Args:
            value: 用户输入
            max_length: 最大长度
            allow_empty: 是否允许空值

        Returns:
            bool: 是否有效

        Raises:
            ValueError: 如果输入无效
        """
        if value is None:
            return allow_empty

        if not isinstance(value, str):
            raise ValueError("输入必须是字符串")

        # 检查长度
        if len(value) > max_length:
            error_msg = f"输入超过最大长度: {len(value)} > {max_length}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 检查空值
        if not value.strip() and not allow_empty:
            raise ValueError("输入不能为空")

        # 检查危险字符 (null字节等)
        dangerous_chars = ['\x00', '\x1a']
        for char in dangerous_chars:
            if char in value:
                error_msg = f"输入包含危险字符"
                logger.error(error_msg)
                raise ValueError(error_msg)

        return True

    @staticmethod
    def sanitize_like_pattern(pattern: str) -> str:
        """
        清理LIKE模式中的通配符

        Args:
            pattern: 原始模式

        Returns:
            str: 清理后的模式
        """
        # 转义SQL通配符
        pattern = pattern.replace('\\', '\\\\')
        pattern = pattern.replace('_', '\\_')
        pattern = pattern.replace('%', '\\%')
        return pattern


class SafeQuery:
    """安全查询工具"""

    def __init__(self, db_connection):
        """
        初始化安全查询工具

        Args:
            db_connection: 数据库连接
        """
        self.conn = db_connection
        self.validator = SecurityValidator()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        安全执行查询

        Args:
            query: SQL查询
            params: 查询参数

        Returns:
            sqlite3.Cursor: 游标对象
        """
        # 验证SQL安全性
        self.validator.validate_sql(query)

        # 使用参数化查询
        cursor = self.conn.execute(query, params)
        return cursor

    def fetch_one(self, query: str, params: tuple = ()):
        """
        获取单行结果

        Args:
            query: SQL查询
            params: 查询参数

        Returns:
            Optional[dict]: 结果行或None
        """
        cursor = self.execute(query, params)
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        """
        获取所有结果

        Args:
            query: SQL查询
            params: 查询参数

        Returns:
            List[dict]: 结果列表
        """
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def search_like(self,
                   table: str,
                   field: str,
                   pattern: str) -> List[Dict]:
        """
        安全的LIKE搜索

        Args:
            table: 表名
            field: 字段名
            pattern: 搜索模式

        Returns:
            List[dict]: 匹配的行
        """
        # 清理模式
        safe_pattern = self.validator.sanitize_like_pattern(pattern)

        # 验证表名和字段名 (防止注入)
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
            raise ValueError(f"无效的表名: {table}")

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', field):
            raise ValueError(f"无效的字段名: {field}")

        query = f"SELECT * FROM {table} WHERE {field} LIKE ? ESCAPE '\\'"
        return self.fetch_all(query, (f"%{safe_pattern}%",))

    def insert_safe(self, table: str, data: Dict[str, Any]) -> int:
        """
        安全插入数据

        Args:
            table: 表名
            data: 数据字典 {字段: 值}

        Returns:
            int: 插入的行ID
        """
        # 验证表名
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
            raise ValueError(f"无效的表名: {table}")

        # 构建SQL
        fields = list(data.keys())
        placeholders = ', '.join(['?'] * len(fields))
        field_names = ', '.join(fields)

        query = f"INSERT INTO {table} ({field_names}) VALUES ({placeholders})"

        # 执行插入
        cursor = self.execute(query, tuple(data.values()))
        return cursor.lastrowid

    def update_safe(self,
                   table: str,
                   data: Dict[str, Any],
                   where: str,
                   where_params: tuple = ()) -> int:
        """
        安全更新数据

        Args:
            table: 表名
            data: 要更新的数据
            where: WHERE子句 (参数化)
            where_params: WHERE参数

        Returns:
            int: 影响的行数
        """
        # 验证表名
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
            raise ValueError(f"无效的表名: {table}")

        # 构建SET子句
        set_clause = ', '.join([f"{field} = ?" for field in data.keys()])

        query = f"UPDATE {table} SET {set_clause} WHERE {where}"

        # 合并参数
        params = list(data.values()) + list(where_params)

        # 执行更新
        cursor = self.execute(query, tuple(params))
        return cursor.rowcount


def safe_filepath_operation(filepath: str):
    """
    文件路径操作装饰器 - 自动验证路径安全性

    Args:
        filepath: 文件路径

    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 验证路径
            SecurityValidator.validate_filepath(filepath)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    import sqlite3

    # 创建内存数据库测试
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE test (
            id INTEGER PRIMARY KEY,
            name TEXT,
            filepath TEXT
        )
    """)

    # 创建安全查询工具
    safe_query = SafeQuery(conn)

    # 安全插入
    try:
        row_id = safe_query.insert_safe("test", {
            "name": "测试数据",
            "filepath": "recordings/test.wav"
        })
        print(f"插入行ID: {row_id}")
    except ValueError as e:
        print(f"插入失败: {e}")

    # 安全搜索
    try:
        results = safe_query.search_like("test", "name", "测试")
        print(f"搜索结果: {results}")
    except ValueError as e:
        print(f"搜索失败: {e}")

    # 测试路径遍历检测
    try:
        SecurityValidator.validate_filepath("../../etc/passwd")
        print("路径验证失败 - 应该不会到这里")
    except ValueError as e:
        print(f"路径遍历检测成功: {e}")

    conn.close()
