"""
测试运行器

运行所有测试:
    python -m tests.runner

运行特定测试:
    python -m tests.runner test_core
    python -m tests.runner test_jitter_buffer
"""
import sys
import os
import subprocess

# 添加项目根目录到路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


def run_tests(module=None):
    """运行测试"""
    import pytest

    # 测试目录
    test_dir = os.path.join(ROOT_DIR, "tests")

    # 构建参数
    args = [test_dir, "-v", "--tb=short"]

    if module:
        # 运行特定模块
        test_file = os.path.join(test_dir, f"test_{module}.py")
        if os.path.exists(test_file):
            args = [test_file, "-v", "--tb=short"]
        else:
            print(f"测试文件不存在: {test_file}")
            return

    print(f"运行测试: {' '.join(args)}")
    print("=" * 60)

    # 运行
    result = pytest.main(args)

    return result


def main():
    """主函数"""
    # 获取命令行参数
    module = None
    if len(sys.argv) > 1:
        module = sys.argv[1]

    result = run_tests(module)

    # 返回状态码
    sys.exit(result)


if __name__ == "__main__":
    main()
