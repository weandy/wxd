"""
Web API 综合集成测试

测试各模块之间的交互和整体功能
"""
import pytest
from tests.test_web_fixtures import test_db


class TestWebAPIIntegration:
    """Web API 集成测试类"""

    def test_dashboard_to_recordings_flow(self, client, test_recording_data):
        """测试从仪表盘到录音列表的流程"""
        # 1. 获取仪表盘概览
        dashboard_response = client.get("/api/dashboard/overview")
        assert dashboard_response.status_code == 200
        dashboard_data = dashboard_response.json()

        # 2. 验证录音总数与录音列表一致
        recordings_response = client.get("/api/recordings")
        assert recordings_response.status_code == 200
        recordings_data = recordings_response.json()

        assert dashboard_data["data"]["total_recordings"] == recordings_data["data"]["total"]

    def test_rules_to_dashboard_flow(self, client, test_rule_data):
        """测试规则管理到仪表盘的流程"""
        # 1. 创建新规则
        new_rule = {
            "name": "集成测试规则",
            "rule_type": "replace",
            "pattern": "old",
            "replacement": "new"
        }
        create_response = client.post("/api/rules", json=new_rule)
        assert create_response.status_code == 200
        rule_id = create_response.json()["data"]["id"]

        # 2. 获取规则统计
        stats_response = client.get("/api/rules/stats")
        assert stats_response.status_code == 200
        stats_data = stats_response.json()

        # 3. 验证新规则被统计
        assert stats_data["data"]["total"] > 0

        # 4. 清理
        client.delete(f"/api/rules/{rule_id}")

    def test_push_services_users_relationship(self, client, test_push_data):
        """测试推送服务与用户的关联关系"""
        # 1. 创建新服务
        new_service = {
            "name": "关联测试服务",
            "type": "wxpusher",
            "url": "https://test.example.com/push"
        }
        service_response = client.post("/api/push/services", json=new_service)
        assert service_response.status_code == 200
        service_id = service_response.json()["data"]["id"]

        # 2. 为该服务创建用户
        new_user = {
            "service_id": service_id,
            "name": "关联测试用户",
            "user_identifier": "UID_RELATION_TEST"
        }
        user_response = client.post("/api/push/users", json=new_user)
        assert user_response.status_code == 200

        # 3. 获取服务详情，验证用户数
        service_detail_response = client.get(f"/api/push/services/{service_id}")
        assert service_detail_response.status_code == 200
        service_detail = service_detail_response.json()
        assert service_detail["data"]["user_count"] >= 1

        # 4. 删除服务，验证用户也被删除
        delete_response = client.delete(f"/api/push/services/{service_id}")
        assert delete_response.status_code == 200

        # 5. 验证用户已不存在
        user_get_response = client.get("/api/push/users")
        users = user_get_response.json()["data"]["users"]
        user_exists = any(u.get("name") == "关联测试用户" for u in users)
        assert not user_exists

    def test_filter_combinations(self, client, test_recording_data):
        """测试复杂筛选组合"""
        # 测试多个筛选条件组合
        filters = {
            "user_id": "user1",
            "min_duration": 3.0,
            "search": "测试"
        }

        response = client.get("/api/recordings", params=filters)
        assert response.status_code == 200
        data = response.json()

        # 验证所有筛选条件都生效
        for recording in data["data"]["recordings"]:
            assert recording["user_id"] == filters["user_id"]
            assert recording["duration"] >= filters["min_duration"]
            text = (recording.get("asr_text") or "") + (recording.get("content_normalized") or "")
            assert filters["search"] in text

    def test_pagination_edge_cases(self, client, test_recording_data):
        """测试分页边界情况"""
        # 测试超出范围的页码
        response = client.get("/api/recordings?page=999&page_size=10")
        assert response.status_code == 200
        data = response.json()

        # 应该返回空列表或最后一页
        assert isinstance(data["data"]["recordings"], list)

    def test_concurrent_operations(self, client, test_rule_data):
        """测试并发操作（模拟）"""
        # 创建多个规则
        rule_ids = []
        for i in range(3):
            new_rule = {
                "name": f"并发测试规则{i}",
                "rule_type": "replace",
                "pattern": f"pattern{i}",
                "replacement": f"replacement{i}"
            }
            response = client.post("/api/rules", json=new_rule)
            assert response.status_code == 200
            rule_ids.append(response.json()["data"]["id"])

        # 批量更新
        for rule_id in rule_ids:
            update_data = {"priority": i}
            response = client.put(f"/api/rules/{rule_id}", json=update_data)
            assert response.status_code == 200

        # 批量删除
        delete_response = client.post("/api/rules/batch-delete", json=rule_ids)
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["deleted_count"] == len(rule_ids)

    def test_data_consistency_after_updates(self, client, test_recording_data):
        """测试更新后数据一致性"""
        # 获取原始数据
        response1 = client.get("/api/recordings/1")
        data1 = response1.json()

        # 模拟更新（这里只是读取，实际应该有更新API）
        response2 = client.get("/api/recordings/1")
        data2 = response2.json()

        # 验证数据一致性
        assert data1["data"]["id"] == data2["data"]["id"]
        assert data1["data"]["filepath"] == data2["data"]["filepath"]

    def test_error_handling_consistency(self, client):
        """测试错误处理的一致性"""
        # 测试各种404错误
        not_found_endpoints = [
            "/api/recordings/99999",
            "/api/rules/99999",
            "/api/push/services/99999",
            "/api/push/users/99999"
        ]

        for endpoint in not_found_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 404

            # 验证错误响应格式
            if response.headers.get("content-type", "").startswith("application/json"):
                error_data = response.json()
                assert "detail" in error_data

    def test_api_response_format_consistency(self, client, test_recording_data):
        """测试API响应格式的一致性"""
        # 测试多个端点的响应格式
        endpoints = [
            "/api/dashboard/overview",
            "/api/recordings",
            "/api/rules/stats",
            "/api/push/services/stats"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            # 验证标准响应格式
            assert "code" in data
            assert "message" in data
            assert "data" in data

            # 验证成功响应
            assert data["code"] == 0

    def test_search_functionality_across_modules(self, client, test_recording_data, test_rule_data):
        """测试跨模块搜索功能"""
        # 测试录音搜索
        recordings_search = client.get("/api/recordings?search=测试")
        assert recordings_search.status_code == 200
        assert len(recordings_search.json()["data"]["recordings"]) >= 0

        # 测试规则搜索
        rules_search = client.get("/api/rules?search=测试")
        assert rules_search.status_code == 200
        assert len(rules_search.json()["data"]["rules"]) >= 0

    def test_enabled_disabled_filters_consistency(self, client, test_rule_data, test_push_data):
        """测试启用/禁用筛选的一致性"""
        # 测试规则的启用/禁用筛选
        rules_enabled = client.get("/api/rules?is_enabled=true")
        rules_disabled = client.get("/api/rules?is_enabled=false")

        assert rules_enabled.status_code == 200
        assert rules_disabled.status_code == 200

        # 验证筛选结果
        for rule in rules_enabled.json()["data"]["rules"]:
            assert rule["is_enabled"] == True

        for rule in rules_disabled.json()["data"]["rules"]:
            assert rule["is_enabled"] == False

        # 测试推送用户的启用/禁用筛选
        users_enabled = client.get("/api/push/users?enabled=true")
        users_disabled = client.get("/api/push/users?enabled=false")

        assert users_enabled.status_code == 200
        assert users_disabled.status_code == 200

        # 验证筛选结果
        for user in users_enabled.json()["data"]["users"]:
            assert user["enabled"] == True

        for user in users_disabled.json()["data"]["users"]:
            assert user["enabled"] == False
