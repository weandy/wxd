"""
Push API 测试
"""
import pytest


class TestPushAPI:
    """Push API 测试类"""

    def test_push_services_list(self, client, test_push_data):
        """测试获取推送服务列表"""
        response = client.get("/api/push/services")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "services" in data["data"]
        assert isinstance(data["data"]["services"], list)

    def test_push_services_get_stats(self, client, test_push_data):
        """测试获取推送统计"""
        response = client.get("/api/push/services/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "total_services" in data["data"]
        assert "enabled_services" in data["data"]
        assert "total_users" in data["data"]
        assert "enabled_users" in data["data"]
        assert "by_type" in data["data"]

    def test_push_services_get_single(self, client, test_push_data):
        """测试获取单个服务详情"""
        response = client.get("/api/push/services/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["id"] == 1
        assert data["data"]["name"] == "测试WxPusher"

    def test_push_services_get_not_found(self, client):
        """测试获取不存在的服务"""
        response = client.get("/api/push/services/99999")

        assert response.status_code == 404

    def test_push_services_create(self, client):
        """测试创建推送服务"""
        new_service = {
            "name": "新测试服务",
            "type": "wxpusher",
            "url": "https://test.example.com/push",
            "token": "test_token_123",
            "config": "{}",
            "enabled": True
        }

        response = client.post("/api/push/services", json=new_service)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "id" in data["data"]

    def test_push_services_create_missing_fields(self, client):
        """测试创建服务缺少必填字段"""
        incomplete_service = {
            "name": "不完整服务"
            # 缺少 type 和 url
        }

        response = client.post("/api/push/services", json=incomplete_service)

        assert response.status_code == 422

    def test_push_services_update(self, client, test_push_data):
        """测试更新推送服务"""
        update_data = {
            "name": "更新后的服务名",
            "enabled": False
        }

        response = client.put("/api/push/services/1", json=update_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

    def test_push_services_update_not_found(self, client):
        """测试更新不存在的服务"""
        update_data = {"name": "测试"}

        response = client.put("/api/push/services/99999", json=update_data)

        assert response.status_code == 404

    def test_push_services_delete(self, client, test_push_data):
        """测试删除推送服务"""
        # 注意：删除服务会同时删除关联用户
        response = client.delete("/api/push/services/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

        # 验证服务已被删除
        get_response = client.get("/api/push/services/1")
        assert get_response.status_code == 404

    def test_push_services_delete_not_found(self, client):
        """测试删除不存在的服务"""
        response = client.delete("/api/push/services/99999")

        assert response.status_code == 404

    def test_push_services_toggle(self, client, test_push_data):
        """测试切换服务状态"""
        # 获取原始状态
        get_response = client.get("/api/push/services/1")
        original_status = get_response.json()["data"]["enabled"]

        # 切换状态
        response = client.post("/api/push/services/toggle", json=1)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["enabled"] != original_status

    def test_push_services_toggle_not_found(self, client):
        """测试切换不存在的服务状态"""
        response = client.post("/api/push/services/toggle", json=99999)

        assert response.status_code == 404

    def test_push_users_list(self, client, test_push_data):
        """测试获取推送用户列表"""
        response = client.get("/api/push/users")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "users" in data["data"]
        assert isinstance(data["data"]["users"], list)

    def test_push_users_filter_by_service(self, client, test_push_data):
        """测试按服务筛选用户"""
        response = client.get("/api/push/users?service_id=1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的用户都属于服务1
        for user in data["data"]["users"]:
            assert user["service_id"] == 1

    def test_push_users_filter_by_enabled(self, client, test_push_data):
        """测试按启用状态筛选用户"""
        response = client.get("/api/push/users?enabled=true")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的用户都是启用状态
        for user in data["data"]["users"]:
            assert user["enabled"] == True

    def test_push_users_get_single(self, client, test_push_data):
        """测试获取单个用户详情"""
        response = client.get("/api/push/users/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["id"] == 1
        assert data["data"]["name"] == "测试用户1"

    def test_push_users_get_not_found(self, client):
        """测试获取不存在的用户"""
        response = client.get("/api/push/users/99999")

        assert response.status_code == 404

    def test_push_users_create(self, client, test_push_data):
        """测试创建推送用户"""
        new_user = {
            "service_id": 1,
            "name": "新测试用户",
            "user_identifier": "UID_NEW_001",
            "keywords": "test,keyword",
            "enabled": True
        }

        response = client.post("/api/push/users", json=new_user)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "id" in data["data"]

    def test_push_users_create_missing_fields(self, client):
        """测试创建用户缺少必填字段"""
        incomplete_user = {
            "name": "不完整用户"
            # 缺少 service_id, user_identifier
        }

        response = client.post("/api/push/users", json=incomplete_user)

        assert response.status_code == 422

    def test_push_users_create_invalid_service(self, client):
        """测试创建用户时指定不存在的服务"""
        new_user = {
            "service_id": 99999,
            "name": "测试用户",
            "user_identifier": "UID_TEST"
        }

        response = client.post("/api/push/users", json=new_user)

        assert response.status_code == 404

    def test_push_users_update(self, client, test_push_data):
        """测试更新推送用户"""
        update_data = {
            "name": "更新后的用户名",
            "keywords": "updated,keywords"
        }

        response = client.put("/api/push/users/1", json=update_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

    def test_push_users_update_not_found(self, client):
        """测试更新不存在的用户"""
        update_data = {"name": "测试"}

        response = client.put("/api/push/users/99999", json=update_data)

        assert response.status_code == 404

    def test_push_users_delete(self, client, test_push_data):
        """测试删除推送用户"""
        response = client.delete("/api/push/users/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

        # 验证用户已被删除
        get_response = client.get("/api/push/users/1")
        assert get_response.status_code == 404

    def test_push_users_delete_not_found(self, client):
        """测试删除不存在的用户"""
        response = client.delete("/api/push/users/99999")

        assert response.status_code == 404

    def test_push_users_toggle(self, client, test_push_data):
        """测试切换用户状态"""
        # 获取原始状态
        get_response = client.get("/api/push/users/1")
        original_status = get_response.json()["data"]["enabled"]

        # 切换状态
        response = client.post("/api/push/users/toggle", json=1)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["enabled"] != original_status

    def test_push_users_toggle_not_found(self, client):
        """测试切换不存在的用户状态"""
        response = client.post("/api/push/users/toggle", json=99999)

        assert response.status_code == 404

    def test_push_test_with_service(self, client, test_push_data):
        """测试推送功能（服务级别）"""
        test_data = {
            "service_id": 1,
            "message": "这是一条测试消息"
        }

        response = client.post("/api/push/test", json=test_data)

        # 注意：实际推送可能会失败，因为没有真实的推送服务
        # 这里只测试API是否能正确处理请求
        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "results" in data["data"]

    def test_push_test_with_user(self, client, test_push_data):
        """测试推送功能（指定用户）"""
        test_data = {
            "service_id": 1,
            "user_id": 1,
            "message": "指定用户测试消息"
        }

        response = client.post("/api/push/test", json=test_data)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0

    def test_push_test_service_not_found(self, client):
        """测试推送时服务不存在"""
        test_data = {
            "service_id": 99999,
            "message": "测试消息"
        }

        response = client.post("/api/push/test", json=test_data)

        assert response.status_code == 404

    def test_push_test_empty_message(self, client, test_push_data):
        """测试推送空消息"""
        test_data = {
            "service_id": 1,
            "message": ""
        }

        # 空消息应该也能处理
        response = client.post("/api/push/test", json=test_data)

        assert response.status_code == 200
