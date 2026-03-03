"""
BSHT Bot Web 平台 - 全面功能测试（无代理版本）
"""
import requests
import json
from datetime import datetime

# 禁用代理
session = requests.Session()
session.trust_env = False

BASE_URL = "http://localhost:8000"

# 测试结果
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": []
}


def test(name, func):
    """测试包装器"""
    test_results["total"] += 1
    print(f"\n{'='*50}")
    print(f"测试: {name}")
    print(f"{'='*50}")
    try:
        func()
        test_results["passed"] += 1
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        test_results["failed"] += 1
        test_results["errors"].append({"test": name, "error": str(e)})
        print(f"[FAIL] {name} - {e}")
        return False
    except Exception as e:
        test_results["failed"] += 1
        test_results["errors"].append({"test": name, "error": str(e)})
        print(f"[ERROR] {name} - {e}")
        return False


def assert_status(response, expected_status, message=""):
    """断言状态码"""
    assert response.status_code == expected_status, \
        f"{message}: 期望状态码 {expected_status}, 实际 {response.status_code}"


def assert_json_success(response, message=""):
    """断言 JSON 响应成功"""
    assert_status(response, 200, message)
    data = response.json()
    assert "code" in data, f"{message}: 响应缺少 'code' 字段"
    assert data["code"] == 0, f"{message}: 响应 code 不为 0，返回: {data}"
    return data


# Phase 1: 健康检查
def test_health():
    """健康检查"""
    response = session.get(f"{BASE_URL}/health", timeout=3)
    assert_status(response, 200, "健康检查")
    data = response.json()
    assert data["status"] == "ok", "状态检查失败"
    print(f"  服务: {data['service']}")


# Phase 2: 录音管理
def test_recordings_stats():
    """录音统计"""
    response = session.get(f"{BASE_URL}/api/recordings/stats", timeout=5)
    data = assert_json_success(response, "录音统计")
    print(f"  总录音: {data['data'].get('total', 0)}")
    print(f"  今日录音: {data['data'].get('today', 0)}")


def test_recordings_list():
    """录音列表"""
    response = session.get(f"{BASE_URL}/api/recordings?limit=10", timeout=5)
    data = assert_json_success(response, "录音列表")
    print(f"  返回数量: {len(data['data'].get('items', []))}")


# Phase 3: 统计仪表板
def test_dashboard_overview():
    """仪表板概览"""
    response = session.get(f"{BASE_URL}/api/dashboard/overview", timeout=5)
    data = assert_json_success(response, "仪表板概览")
    print(f"  总录音: {data['data'].get('total_recordings', 0)}")
    print(f"  总识别: {data['data'].get('total_recognized', 0)}")
    print(f"  活跃频道: {data['data'].get('active_channels', 0)}")


def test_dashboard_trends():
    """仪表板趋势"""
    response = session.get(f"{BASE_URL}/api/dashboard/trends", timeout=5)
    data = assert_json_success(response, "仪表板趋势")
    print(f"  趋势数据点: {len(data['data'].get('daily', []))}")


# Phase 4: 纠错规则
def test_rules_stats():
    """规则统计"""
    response = session.get(f"{BASE_URL}/api/rules/stats", timeout=3)
    data = assert_json_success(response, "规则统计")
    print(f"  总规则: {data['data'].get('total', 0)}")
    print(f"  启用规则: {data['data'].get('enabled', 0)}")


def test_rules_list():
    """规则列表"""
    response = session.get(f"{BASE_URL}/api/rules", timeout=3)
    data = assert_json_success(response, "规则列表")
    print(f"  规则数量: {data['data'].get('total', 0)}")


# Phase 5: 推送服务
def test_push_config():
    """推送配置"""
    response = session.get(f"{BASE_URL}/api/push/config", timeout=3)
    data = assert_json_success(response, "推送配置")
    print(f"  启用状态: {data['data'].get('enabled', False)}")


def test_push_stats():
    """推送统计"""
    response = session.get(f"{BASE_URL}/api/push/stats", timeout=3)
    data = assert_json_success(response, "推送统计")
    print(f"  总推送: {data['data'].get('total_pushes', 0)}")


def test_push_targets():
    """推送目标"""
    response = session.get(f"{BASE_URL}/api/push/targets", timeout=3)
    data = assert_json_success(response, "推送目标")
    print(f"  目标数量: {data['data'].get('total', 0)}")


# Phase 6: 广播任务与音频库
def test_broadcast_stats():
    """广播统计"""
    response = session.get(f"{BASE_URL}/api/broadcast/stats", timeout=3)
    data = assert_json_success(response, "广播统计")
    print(f"  总任务: {data['data'].get('total', 0)}")


def test_broadcast_tasks():
    """广播任务列表"""
    response = session.get(f"{BASE_URL}/api/broadcast/tasks", timeout=3)
    data = assert_json_success(response, "广播任务列表")
    print(f"  任务数量: {data['data'].get('total', 0)}")


def test_audio_library_stats():
    """音频库统计"""
    response = session.get(f"{BASE_URL}/api/audio-library/stats", timeout=3)
    data = assert_json_success(response, "音频库统计")
    print(f"  总音频: {data['data'].get('total_audio', 0)}")


def test_audio_library():
    """音频库列表"""
    response = session.get(f"{BASE_URL}/api/audio-library", timeout=3)
    data = assert_json_success(response, "音频库列表")
    print(f"  音频数量: {data['data'].get('total', 0)}")


# Phase 7: 机器人监控
def test_monitor_overview():
    """监控概览"""
    response = session.get(f"{BASE_URL}/api/monitor/overview", timeout=10)
    data = assert_json_success(response, "监控概览")
    print(f"  24h录音: {data['data'].get('recordings_24h', 0)}")
    print(f"  活跃频道: {data['data'].get('active_channels_7d', 0)}")
    print(f"  CPU: {data['data']['system'].get('cpu_percent', 0)}%")
    print(f"  内存: {data['data']['system'].get('memory_percent', 0)}%")


def test_monitor_logs():
    """监控日志"""
    response = session.get(f"{BASE_URL}/api/monitor/logs?limit=5", timeout=5)
    data = assert_json_success(response, "监控日志")
    print(f"  日志数量: {data['data'].get('total', 0)}")


def test_monitor_metrics():
    """性能指标"""
    response = session.get(f"{BASE_URL}/api/monitor/metrics", timeout=10)
    data = assert_json_success(response, "性能指标")
    print(f"  7天趋势: {len(data['data'].get('trend_7d', []))}天")
    print(f"  每小时统计: {len(data['data'].get('hourly_stats', []))}小时")


def test_monitor_channels():
    """频道监控"""
    response = session.get(f"{BASE_URL}/api/monitor/channels", timeout=10)
    data = assert_json_success(response, "频道监控")
    print(f"  频道数量: {data['data'].get('total', 0)}")


# 运行所有测试
def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - 全面功能测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {BASE_URL}")

    # Phase 1
    print("\n" + "="*60)
    print("Phase 1: 基础设施")
    print("="*60)
    test("健康检查", test_health)

    # Phase 2
    print("\n" + "="*60)
    print("Phase 2: 录音管理")
    print("="*60)
    test("录音统计", test_recordings_stats)
    test("录音列表", test_recordings_list)

    # Phase 3
    print("\n" + "="*60)
    print("Phase 3: 统计仪表板")
    print("="*60)
    test("仪表板概览", test_dashboard_overview)
    test("仪表板趋势", test_dashboard_trends)

    # Phase 4
    print("\n" + "="*60)
    print("Phase 4: 纠错规则")
    print("="*60)
    test("规则统计", test_rules_stats)
    test("规则列表", test_rules_list)

    # Phase 5
    print("\n" + "="*60)
    print("Phase 5: 推送服务")
    print("="*60)
    test("推送配置", test_push_config)
    test("推送统计", test_push_stats)
    test("推送目标", test_push_targets)

    # Phase 6
    print("\n" + "="*60)
    print("Phase 6: 广播任务与音频库")
    print("="*60)
    test("广播统计", test_broadcast_stats)
    test("广播任务列表", test_broadcast_tasks)
    test("音频库统计", test_audio_library_stats)
    test("音频库列表", test_audio_library)

    # Phase 7
    print("\n" + "="*60)
    print("Phase 7: 机器人监控")
    print("="*60)
    test("监控概览", test_monitor_overview)
    test("监控日志", test_monitor_logs)
    test("性能指标", test_monitor_metrics)
    test("频道监控", test_monitor_channels)

    # 打印结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"总测试数: {test_results['total']}")
    print(f"通过: {test_results['passed']} ({test_results['passed']/test_results['total']*100:.1f}%)")
    print(f"失败: {test_results['failed']} ({test_results['failed']/test_results['total']*100:.1f}%)")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if test_results['errors']:
        print("\n失败详情:")
        for error in test_results['errors']:
            print(f"  - {error['test']}: {error['error']}")

    return test_results['failed'] == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
