"""
Rules API 测试
"""
import pytest


class TestRulesAPI:
    """Rules API 测试类"""

    def test_rules_list_default(self, client, test_rule_data):
        """测试获取规则列表（默认参数）"""
        response = client.get("/api/rules")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "rules" in data["data"]
        assert "total" in data["data"]
        assert isinstance(data["data"]["rules"], list)

    def test_rules_list_with_pagination(self, client, test_rule_data):
        """测试分页功能"""
        response = client.get("/api/rules?page=1&page_size=2")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert len(data["data"]["rules"]) <= 2
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2

    def test_rules_filter_by_type(self, client, test_rule_data):
        """测试按类型筛选"""
        response = client.get("/api/rules?rule_type=replace")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的规则都是replace类型
        for rule in data["data"]["rules"]:
            assert rule["rule_type"] == "replace"

    def test_rules_filter_by_enabled(self, client, test_rule_data):
        """测试按启用状态筛选"""
        response = client.get("/api/rules?is_enabled=true")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的规则都是启用状态
        for rule in data["data"]["rules"]:
            assert rule["is_enabled"] == True

    def test_rules_search(self, client, test_rule_data):
        """测试搜索功能"""
        response = client.get("/api/rules?search=测试")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证搜索结果包含关键词
        for rule in data["data"]["rules"]:
            text = (rule.get("name") or "") + (rule.get("pattern") or "") + (rule.get("description") or "")
            assert "测试" in text

    def test_rules_get_stats(self, client, test_rule_data):
        """测试获取统计数据"""
        response = client.get("/api/rules/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "total" in data["data"]
        assert "enabled" in data["data"]
        assert "disabled" in data["data"]
        assert "by_type" in data["data"]
        assert data["data"]["total"] >= 0

    def test_rules_get_categories(self, client, test_rule_data):
        """测试获取分类列表"""
        response = client.get("/api/rules/categories")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "categories" in data["data"]
        assert isinstance(data["data"]["categories"], list)

    def test_rules_get_single(self, client, test_rule_data):
        """测试获取单个规则详情"""
        response = client.get("/api/rules/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert data["data"]["id"] == 1

    def test_rules_get_not_found(self, client):
        """测试获取不存在的规则"""
        response = client.get("/api/rules/99999")

        assert response.status_code == 404

    def test_rules_create(self, client):
        """测试创建规则"""
        new_rule = {
            "name": "测试创建规则",
            "rule_type": "replace",
            "pattern": "old",
            "replacement": "new",
            "description": "测试规则创建功能",
            "category": "test",
            "priority": 5,
            "is_enabled": True
        }

        response = client.post("/api/rules", json=new_rule)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "id" in data["data"]

    def test_rules_create_missing_required_fields(self, client):
        """测试创建规则缺少必填字段"""
        incomplete_rule = {
            "name": "不完整规则"
            # 缺少 rule_type 和 pattern
        }

        response = client.post("/api/rules", json=incomplete_rule)

        # 应该返回验证错误
        assert response.status_code == 422

    def test_rules_update(self, client, test_rule_data):
        """测试更新规则"""
        update_data = {
            "name": "更新后的规则名",
            "priority": 10
        }

        response = client.put("/api/rules/1", json=update_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

    def test_rules_update_not_found(self, client):
        """测试更新不存在的规则"""
        update_data = {"name": "测试"}

        response = client.put("/api/rules/99999", json=update_data)

        assert response.status_code == 404

    def test_rules_delete(self, client, test_rule_data):
        """测试删除规则"""
        response = client.delete("/api/rules/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

        # 验证规则已被删除
        get_response = client.get("/api/rules/1")
        assert get_response.status_code == 404

    def test_rules_delete_not_found(self, client):
        """测试删除不存在的规则"""
        response = client.delete("/api/rules/99999")

        assert response.status_code == 404

    def test_rules_batch_delete(self, client, test_rule_data):
        """测试批量删除规则"""
        rule_ids = [1, 2]

        response = client.post("/api/rules/batch-delete", json=rule_ids)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["deleted_count"] == 2

    def test_rules_toggle(self, client, test_rule_data):
        """测试切换规则状态"""
        # 获取原始状态
        get_response = client.get("/api/rules/1")
        original_status = get_response.json()["data"]["is_enabled"]

        # 切换状态
        response = client.post("/api/rules/toggle", json=1)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["is_enabled"] != original_status

    def test_rules_toggle_not_found(self, client):
        """测试切换不存在的规则状态"""
        response = client.post("/api/rules/toggle", json=99999)

        assert response.status_code == 404

    def test_rules_test(self, client, test_rule_data):
        """测试规则应用"""
        test_data = {
            "text": "这是一个测试内容"
        }

        response = client.post("/api/rules/test", json=test_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "original_text" in data["data"]
        assert "result_text" in data["data"]
        assert "applied_rules" in data["data"]
        assert data["data"]["original_text"] == test_data["text"]

    def test_rules_test_with_specific_rules(self, client, test_rule_data):
        """测试指定规则ID"""
        test_data = {
            "text": "测试内容",
            "rule_ids": [1]
        }

        response = client.post("/api/rules/test", json=test_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

    def test_rules_test_empty_text(self, client):
        """测试空文本"""
        test_data = {
            "text": ""
        }

        response = client.post("/api/rules/test", json=test_data)

        # 空文本应该也能处理
        assert response.status_code == 200
