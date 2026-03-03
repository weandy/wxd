"""
Dashboard API 测试
"""
import pytest


class TestDashboardAPI:
    """Dashboard API 测试类"""

    def test_dashboard_overview(self, client, test_recording_data):
        """测试获取概览数据"""
        response = client.get("/api/dashboard/overview")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "total_recordings" in data["data"]
        assert "recognition_rate" in data["data"]
        assert "active_users_7d" in data["data"]
        assert data["data"]["total_recordings"] >= 0

    def test_dashboard_trend(self, client, test_recording_data):
        """测试获取趋势数据"""
        response = client.get("/api/dashboard/trend?days=7")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "days" in data["data"]
        assert "data" in data["data"]
        assert data["data"]["days"] == 7
        assert isinstance(data["data"]["data"], list)

    def test_dashboard_trend_custom_days(self, client):
        """测试自定义天数趋势"""
        response = client.get("/api/dashboard/trend?days=30")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["days"] == 30

    def test_dashboard_signal_types(self, client, test_recording_data):
        """测试获取信号类型分布"""
        response = client.get("/api/dashboard/signal-types")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "signal_types" in data["data"]
        assert isinstance(data["data"]["signal_types"], list)

    def test_dashboard_top_users(self, client, test_recording_data):
        """测试获取活跃用户排行"""
        response = client.get("/api/dashboard/top-users?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "top_users" in data["data"]
        assert isinstance(data["data"]["top_users"], list)

    def test_dashboard_top_users_custom_limit(self, client):
        """测试自定义用户数量"""
        response = client.get("/api/dashboard/top-users?limit=5")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert len(data["data"]["top_users"]) <= 5

    def test_dashboard_endpoints_integrated(self, client, test_recording_data):
        """测试所有仪表盘端点的集成"""
        endpoints = [
            "/api/dashboard/overview",
            "/api/dashboard/trend?days=7",
            "/api/dashboard/signal-types",
            "/api/dashboard/top-users?limit=10"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "data" in data
