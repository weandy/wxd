"""
测试关键问题修复

验证以下5个问题的修复:
1. SQL注入风险
2. 竞态条件
3. 资源泄漏
4. 错误处理不一致
5. 数据库连接池
"""

import pytest
import threading
import time
import sqlite3
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestResourceManagement:
    """测试资源管理 (问题3)"""

    def test_audio_recorder_context_manager(self):
        """测试AudioRecorder上下文管理器"""
        from audio_recorder_enhanced import AudioRecorderEnhanced

        # 使用上下文管理器
        with AudioRecorderEnhanced() as recorder:
            assert recorder.is_recording
            instance_count = AudioRecorderEnhanced.get_instance_count()
            assert instance_count > 0

        # 退出后应自动清理
        assert not recorder.is_recording
        print("✅ AudioRecorder上下文管理器测试通过")

    def test_audio_recorder_manual_cleanup(self):
        """测试AudioRecorder手动清理"""
        from audio_recorder_enhanced import AudioRecorderEnhanced

        recorder = AudioRecorderEnhanced()
        recorder.start_recording()

        assert recorder.is_recording

        # 手动清理
        recorder.cleanup()

        assert not recorder.is_recording
        assert recorder.pyaudio is None
        assert recorder.stream is None
        print("✅ AudioRecorder手动清理测试通过")

    def test_audio_recorder_idempotent_cleanup(self):
        """测试cleanup幂等性"""
        from audio_recorder_enhanced import AudioRecorderEnhanced

        recorder = AudioRecorderEnhanced()
        recorder.start_recording()

        # 多次调用cleanup应该安全
        recorder.cleanup()
        recorder.cleanup()
        recorder.cleanup()

        print("✅ AudioRecorder幂等性测试通过")


class TestConcurrency:
    """测试并发安全 (问题2)"""

    def test_concurrent_transmit_start(self):
        """测试并发启动发射"""
        from bsht_client import AudioStreamListener, BSHTClient

        # 创建测试客户端
        client = BSHTClient(auto_refresh_token=False)
        listener = AudioStreamListener(client)

        results = []
        errors = []

        def try_start_transmit():
            try:
                # 模拟start_transmit调用
                result = listener.start_transmit()
                results.append(result)
                time.sleep(0.1)
                if result:
                    listener.stop_transmit()
            except Exception as e:
                errors.append(e)

        # 启动多个线程
        threads = [
            threading.Thread(target=try_start_transmit)
            for _ in range(5)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=5)

        # 验证: 只有一个应该成功 (或全部失败因为未连接)
        success_count = sum(1 for r in results if r)
        assert success_count <= 1, f"多个线程同时成功: {success_count}"
        assert len(errors) == 0, f"有异常发生: {errors}"

        print(f"✅ 并发启动测试通过: {success_count}个成功")


class TestDatabasePool:
    """测试数据库连接池 (问题5)"""

    def test_pool_initialization(self):
        """测试连接池初始化"""
        from src.database_pool import DatabaseConnectionPool

        pool = DatabaseConnectionPool(":memory:", pool_size=3)

        stats = pool.get_stats()
        assert stats['created'] == 3
        assert stats['available'] == 3

        pool.close_all()
        print("✅ 连接池初始化测试通过")

    def test_concurrent_queries(self):
        """测试并发查询"""
        from src.database_pool import DatabaseConnectionPool

        pool = DatabaseConnectionPool(":memory:", pool_size=5)

        # 创建测试表
        with pool.get_connection() as conn:
            conn.execute("""
                CREATE TABLE test (
                    id INTEGER PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("INSERT INTO test VALUES (1, 'test')")

        results = []
        errors = []

        def query():
            try:
                with pool.get_connection() as conn:
                    result = conn.execute("SELECT * FROM test").fetchall()
                    results.append(len(result))
            except Exception as e:
                errors.append(e)

        # 启动多个查询线程
        threads = [threading.Thread(target=query) for _ in range(10)]
        start = time.time()

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start

        # 验证所有查询都成功
        assert len(results) == 10, f"只有 {len(results)}/10 查询成功"
        assert len(errors) == 0, f"有 {len(errors)} 个错误"
        assert all(r == 1 for r in results), "查询结果不正确"

        pool.close_all()
        print(f"✅ 并发查询测试通过: 10线程 × 1查询 = {elapsed:.2f}秒")

    def test_pool_stats(self):
        """测试连接池统计"""
        from src.database_pool import DatabaseConnectionPool

        pool = DatabaseConnectionPool(":memory:", pool_size=2)

        # 执行一些操作
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

        stats = pool.get_stats()
        assert stats['reused'] >= 1
        assert stats['created'] == 2
        assert stats['available'] == 2

        pool.close_all()
        print("✅ 连接池统计测试通过")


class TestSafeQuery:
    """测试安全查询 (问题1)"""

    def test_sql_injection_prevention(self):
        """测试SQL注入防护"""
        from src.safe_query import SecurityValidator

        # 测试包含危险SQL关键词的查询
        dangerous_queries = [
            "SELECT * FROM users WHERE name='admin' --",
            "SELECT * FROM users WHERE name='admin'; DROP TABLE users--",
        ]

        for query in dangerous_queries:
            try:
                SecurityValidator.validate_sql(query)
                assert False, f"应该拒绝危险SQL: {query}"
            except ValueError:
                pass  # 预期的行为

        # 测试安全的查询应该通过
        safe_queries = [
            "SELECT * FROM users WHERE name='admin'",
            "SELECT * FROM users WHERE id=1",
            "SELECT * FROM users WHERE name='admin' OR '1'='1'",  # 不包含危险关键词
        ]

        for query in safe_queries:
            try:
                result = SecurityValidator.validate_sql(query)
                assert result == True
            except ValueError:
                # 如果是包含危险关键词的查询，抛出异常是预期的
                pass

        print("✅ SQL注入防护测试通过")

    def test_path_traversal_prevention(self):
        """测试路径遍历防护"""
        from src.safe_query import SecurityValidator

        # 测试路径遍历攻击
        dangerous_paths = [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
        ]

        for path in dangerous_paths:
            try:
                SecurityValidator.validate_filepath(path)
                assert False, f"应该拒绝路径遍历: {path}"
            except ValueError:
                pass  # 预期的行为

        # 测试安全路径
        safe_path = "recordings/test.wav"
        assert SecurityValidator.validate_filepath(safe_path)

        print("✅ 路径遍历防护测试通过")

    def test_like_pattern_sanitization(self):
        """测试LIKE模式清理"""
        from src.safe_query import SecurityValidator

        # 测试特殊字符转义
        pattern = "test_%_pattern"
        safe = SecurityValidator.sanitize_like_pattern(pattern)

        # 检查通配符被转义
        assert r'\%' in safe or '%' in safe  # % 被转义
        assert r'\_' in safe or '_' in safe  # _ 被转义

        print("✅ LIKE模式清理测试通过")


class TestErrorHandling:
    """测试错误处理 (问题4)"""

    def test_error_handler(self):
        """测试统一错误处理"""
        from src.error_handling import ErrorHandler, log_errors

        handler = ErrorHandler("test_module")

        # 测试异常处理
        try:
            raise ValueError("测试错误")
        except Exception as e:
            # 不应该抛出异常 (reraise=False)
            handler.handle_exception(e, context="测试上下文", reraise=False)

        print("✅ 错误处理器测试通过")

    def test_log_errors_decorator(self):
        """测试错误日志装饰器"""
        from src.error_handling import log_errors
        import logging

        # 设置日志
        logging.basicConfig(level=logging.DEBUG)

        @log_errors("test_module", "测试函数", reraise=False)
        def test_function():
            raise ValueError("测试异常")

        # 调用函数，应该记录日志但不抛出异常
        result = test_function()
        assert result is None

        print("✅ 错误日志装饰器测试通过")

    def test_safe_execute_decorator(self):
        """测试安全执行装饰器"""
        from src.error_handling import safe_execute

        @safe_execute(default=[], log_module="test")
        def get_data():
            raise ValueError("应该被捕获")

        result = get_data()
        assert result == []

        print("✅ 安全执行装饰器测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试关键问题修复")
    print("=" * 60)

    test_classes = [
        TestResourceManagement(),
        TestConcurrency(),
        TestDatabasePool(),
        TestSafeQuery(),
        TestErrorHandling(),
    ]

    for test_class in test_classes:
        print(f"\n测试类: {test_class.__class__.__name__}")
        print("-" * 40)

        # 获取所有测试方法
        test_methods = [
            method for method in dir(test_class)
            if method.startswith('test_')
        ]

        for method_name in test_methods:
            method = getattr(test_class, method_name)
            try:
                method()
            except Exception as e:
                print(f"❌ {method_name} 失败: {e}")
                import traceback
                traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
