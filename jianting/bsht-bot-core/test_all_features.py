"""
BSHT Bot Web 平台 - 全面功能测试脚本
测试所有 7 个开发阶段的 API 端点和功能
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
session = requests.Session()

# 测试结果统计
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": []
}


def test(name, func):
    """测试包装器"""
    test_results["total"] += 1
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"{'='*60}")
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


def assert_equal(actual, expected, message=""):
    """断言相等"""
    assert actual == expected, f"{message}: 期望 {expected}, 实际 {actual}"


def assert_in(actual, expected, message=""):
    """断言包含"""
    assert expected in actual, f"{message}: '{expected}' 不在 '{actual}' 中"


def assert_status(response, expected_status, message=""):
    """断言状态码"""
    assert response.status_code == expected_status, \
        f"{message}: 期望状态码 {expected_status}, 实际 {response.status_code}"


def assert_json_success(response, message=""):
    """断言 JSON 响应成功"""
    assert_status(response, 200, message)
    data = response.json()
    assert "code" in data, f"{message}: 响应缺少 'code' 字段"
    assert data["code"] == 0, f"{message}: 响应 code 不为 0"
    return data


# ==================== Phase 1: 认证测试 ====================

def test_health_check():
    """测试健康检查"""
    response = session.get(f"{BASE_URL}/health")
    assert_status(response, 200, "健康检查")
    data = response.json()
    assert_equal(data["status"], "ok", "状态检查")
    print(f"  服务: {data['service']}")


def test_login():
    """测试登录"""
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    data = assert_json_success(response, "登录")
    assert "data" in data, "登录响应缺少 data"
    print(f"  用户: {data['data'].get('username', 'N/A')}")


def test_get_current_user():
    """测试获取当前用户"""
    response = session.get(f"{BASE_URL}/api/auth/me")
    data = assert_json_success(response, "获取当前用户")
    assert "data" in data, "响应缺少 data"
    print(f"  当前用户: {data['data'].get('username', 'N/A')}")


# ==================== Phase 2: 录音管理测试 ====================

def test_recordings_list():
    """测试录音列表"""
    response = session.get(f"{BASE_URL}/api/recordings")
    data = assert_json_success(response, "录音列表")
    assert "data" in data, "响应缺少 data"
    print(f"  录音数量: {data['data'].get('total', 0)}")
    return data


def test_recordings_stats():
    """测试录音统计"""
    response = session.get(f"{BASE_URL}/api/recordings/stats")
    data = assert_json_success(response, "录音统计")
    assert "data" in data, "响应缺少 data"
    stats = data["data"]
    print(f"  总录音: {stats.get('total', 0)}")
    print(f"  今日录音: {stats.get('today', 0)}")


# ==================== Phase 3: 统计仪表板测试 ====================

def test_dashboard_overview():
    """测试仪表板概览"""
    response = session.get(f"{BASE_URL}/api/dashboard/overview")
    data = assert_json_success(response, "仪表板概览")
    assert "data" in data, "响应缺少 data"
    print(f"  总录音: {data['data'].get('total_recordings', 0)}")
    print(f"  总识别: {data['data'].get('total_recognized', 0)}")


def test_dashboard_trends():
    """测试仪表板趋势"""
    response = session.get(f"{BASE_URL}/api/dashboard/trends")
    data = assert_json_success(response, "仪表板趋势")
    assert "data" in data, "响应缺少 data"
    print(f"  趋势数据点: {len(data['data'].get('daily', []))}")


# ==================== Phase 4: 纠错规则测试 ====================

def test_rules_list():
    """测试规则列表"""
    response = session.get(f"{BASE_URL}/api/rules")
    data = assert_json_success(response, "规则列表")
    assert "data" in data, "响应缺少 data"
    print(f"  规则数量: {data['data'].get('total', 0)}")
    return data


def test_rules_stats():
    """测试规则统计"""
    response = session.get(f"{BASE_URL}/api/rules/stats")
    data = assert_json_success(response, "规则统计")
    assert "data" in data, "响应缺少 data"
    print(f"  总规则: {data['data'].get('total', 0)}")
    print(f"  启用规则: {data['data'].get('enabled', 0)}")


def test_create_rule():
    """测试创建规则"""
    response = session.post(f"{BASE_URL}/api/rules", json={
        "name": "测试规则",
        "error_pattern": "测试",
        "correction": "测试修正",
        "category": "test",
        "is_enabled": True
    })
    data = assert_json_success(response, "创建规则")
    assert "data" in data, "响应缺少 data"
    assert "id" in data["data"], "响应缺少 id"
    print(f"  创建的规则ID: {data['data']['id']}")
    return data["data"]["id"]


def test_update_rule(rule_id):
    """测试更新规则"""
    response = session.put(f"{BASE_URL}/api/rules/{rule_id}", json={
        "name": "测试规则（已更新）",
        "correction": "测试修正 v2"
    })
    data = assert_json_success(response, "更新规则")
    print(f"  更新后的规则ID: {data['data']['id']}")


def test_delete_rule(rule_id):
    """测试删除规则"""
    response = session.delete(f"{BASE_URL}/api/rules/{rule_id}")
    data = assert_json_success(response, "删除规则")
    print(f"  删除的规则ID: {data['data']['id']}")


# ==================== Phase 5: 推送服务测试 ====================

def test_push_config():
    """测试推送配置"""
    response = session.get(f"{BASE_URL}/api/push/config")
    data = assert_json_success(response, "推送配置")
    assert "data" in data, "响应缺少 data"
    print(f"  配置状态: {data['data'].get('enabled', False)}")


def test_push_targets():
    """测试推送目标"""
    response = session.get(f"{BASE_URL}/api/push/targets")
    data = assert_json_success(response, "推送目标")
    assert "data" in data, "响应缺少 data"
    print(f"  目标数量: {data['data'].get('total', 0)}")


def test_push_stats():
    """测试推送统计"""
    response = session.get(f"{BASE_URL}/api/push/stats")
    data = assert_json_success(response, "推送统计")
    assert "data" in data, "响应缺少 data"
    print(f"  总推送: {data['data'].get('total_pushes', 0)}")


# ==================== Phase 6: 广播任务与音频库测试 ====================

def test_broadcast_stats():
    """测试广播统计"""
    response = session.get(f"{BASE_URL}/api/broadcast/stats")
    data = assert_json_success(response, "广播统计")
    assert "data" in data, "响应缺少 data"
    print(f"  总任务: {data['data'].get('total', 0)}")


def test_broadcast_tasks():
    """测试广播任务列表"""
    response = session.get(f"{BASE_URL}/api/broadcast/tasks")
    data = assert_json_success(response, "广播任务列表")
    assert "data" in data, "响应缺少 data"
    print(f"  任务数量: {data['data'].get('total', 0)}")


def test_audio_library_stats():
    """测试音频库统计"""
    response = session.get(f"{BASE_URL}/api/audio-library/stats")
    data = assert_json_success(response, "音频库统计")
    assert "data" in data, "响应缺少 data"
    print(f"  总音频: {data['data'].get('total_audio', 0)}")


def test_audio_library():
    """测试音频库列表"""
    response = session.get(f"{BASE_URL}/api/audio-library")
    data = assert_json_success(response, "音频库列表")
    assert "data" in data, "响应缺少 data"
    print(f"  音频数量: {data['data'].get('total', 0)}")


# ==================== Phase 7: 机器人监控测试 ====================

def test_monitor_overview():
    """测试监控概览"""
    response = session.get(f"{BASE_URL}/api/monitor/overview")
    data = assert_json_success(response, "监控概览")
    assert "data" in data, "响应缺少 data"
    print(f"  24h录音: {data['data'].get('recordings_24h', 0)}")
    print(f"  活跃频道: {data['data'].get('active_channels_7d', 0)}")
    print(f"  CPU: {data['data']['system'].get('cpu_percent', 0)}%")


def test_monitor_logs():
    """测试监控日志"""
    response = session.get(f"{BASE_URL}/api/monitor/logs?limit=10")
    data = assert_json_success(response, "监控日志")
    assert "data" in data, "响应缺少 data"
    print(f"  日志数量: {data['data'].get('total', 0)}")


def test_monitor_metrics():
    """测试性能指标"""
    response = session.get(f"{BASE_URL}/api/monitor/metrics")
    data = assert_json_success(response, "性能指标")
    assert "data" in data, "响应缺少 data"
    print(f"  7天趋势: {len(data['data'].get('trend_7d', []))}天")
    print(f"  每小时统计: {len(data['data'].get('hourly_stats', []))}小时")


def test_monitor_channels():
    """测试频道监控"""
    response = session.get(f"{BASE_URL}/api/monitor/channels")
    data = assert_json_success(response, "频道监控")
    assert "data" in data, "响应缺少 data"
    print(f"  频道数量: {data['data'].get('total', 0)}")


# ==================== 运行所有测试 ====================

def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - 全面功能测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试服务器: {BASE_URL}")

    # Phase 1: 认证
    print("\n" + "="*60)
    print("Phase 1: 基础设施与认证")
    print("="*60)
    test("健康检查", test_health_check)
    test("登录", test_login)
    test("获取当前用户", test_get_current_user)

    # Phase 2: 录音管理
    print("\n" + "="*60)
    print("Phase 2: 录音管理")
    print("="*60)
    test("录音列表", test_recordings_list)
    test("录音统计", test_recordings_stats)

    # Phase 3: 统计仪表板
    print("\n" + "="*60)
    print("Phase 3: 统计仪表板")
    print("="*60)
    test("仪表板概览", test_dashboard_overview)
    test("仪表板趋势", test_dashboard_trends)

    # Phase 4: 纠错规则
    print("\n" + "="*60)
    print("Phase 4: 纠错规则管理")
    print("="*60)
    test("规则列表", test_rules_list)
    test("规则统计", test_rules_stats)
    test("创建规则", test_create_rule)

    # Phase 5: 推送服务
    print("\n" + "="*60)
    print("Phase 5: 推送服务管理")
    print("="*60)
    test("推送配置", test_push_config)
    test("推送目标", test_push_targets)
    test("推送统计", test_push_stats)

    # Phase 6: 广播任务与音频库
    print("\n" + "="*60)
    print("Phase 6: 广播任务与音频库")
    print("="*60)
    test("广播统计", test_broadcast_stats)
    test("广播任务列表", test_broadcast_tasks)
    test("音频库统计", test_audio_library_stats)
    test("音频库列表", test_audio_library)

    # Phase 7: 机器人监控
    print("\n" + "="*60)
    print("Phase 7: 机器人监控")
    print("="*60)
    test("监控概览", test_monitor_overview)
    test("监控日志", test_monitor_logs)
    test("性能指标", test_monitor_metrics)
    test("频道监控", test_monitor_channels)

    # 打印测试结果
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
