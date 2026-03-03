"""
Recordings API 测试
"""
import pytest


class TestRecordingsAPI:
    """Recordings API 测试类"""

    def test_recordings_list_default(self, client, test_recording_data):
        """测试获取录音列表（默认参数）"""
        response = client.get("/api/recordings")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert "recordings" in data["data"]
        assert "total" in data["data"]
        assert isinstance(data["data"]["recordings"], list)

    def test_recordings_list_with_pagination(self, client, test_recording_data):
        """测试分页功能"""
        response = client.get("/api/recordings?page=1&page_size=2")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert len(data["data"]["recordings"]) <= 2
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2

    def test_recordings_filter_by_user(self, client, test_recording_data):
        """测试按用户筛选"""
        response = client.get("/api/recordings?user_id=user1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的录音都属于 user1
        for recording in data["data"]["recordings"]:
            assert recording["user_id"] == "user1"

    def test_recordings_filter_by_date(self, client, test_recording_data):
        """测试按日期筛选"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        response = client.get(f"/api/recordings?date={today}")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert isinstance(data["data"]["recordings"], list)

    def test_recordings_filter_by_duration(self, client, test_recording_data):
        """测试按时长筛选"""
        response = client.get("/api/recordings?min_duration=5.0")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证返回的录音时长都大于等于5秒
        for recording in data["data"]["recordings"]:
            assert recording["duration"] >= 5.0

    def test_recordings_search(self, client, test_recording_data):
        """测试搜索功能"""
        response = client.get("/api/recordings?search=测试")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证搜索结果包含关键词
        for recording in data["data"]["recordings"]:
            text = (recording.get("asr_text") or "") + (recording.get("content_normalized") or "")
            assert "测试" in text

    def test_recordings_combined_filters(self, client, test_recording_data):
        """测试组合筛选"""
        response = client.get("/api/recordings?user_id=user1&min_duration=3.0&search=测试")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        # 验证所有筛选条件都生效
        for recording in data["data"]["recordings"]:
            assert recording["user_id"] == "user1"
            assert recording["duration"] >= 3.0
            text = (recording.get("asr_text") or "") + (recording.get("content_normalized") or "")
            assert "测试" in text

    def test_recordings_get_single(self, client, test_recording_data):
        """测试获取单个录音详情"""
        response = client.get("/api/recordings/1")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert "data" in data
        assert data["data"]["id"] == 1

    def test_recordings_get_not_found(self, client):
        """测试获取不存在的录音"""
        response = client.get("/api/recordings/99999")

        assert response.status_code == 404

    def test_recordings_batch_delete(self, client, test_recording_data):
        """测试批量删除"""
        # 先获取录音列表
        list_response = client.get("/api/recordings")
        recording_ids = [r["id"] for r in list_response.json()["data"]["recordings"][:2]]

        # 执行批量删除
        response = client.post("/api/recordings/batch-delete", json=recording_ids)

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["deleted_count"] == len(recording_ids)

    def test_recordings_batch_delete_empty_list(self, client):
        """测试批量删除空列表"""
        response = client.post("/api/recordings/batch-delete", json=[])

        # 应该返回错误或空列表处理
        assert response.status_code in [200, 400]

    def test_recordings_pagination_consistency(self, client, test_recording_data):
        """测试分页一致性"""
        # 获取第一页
        response1 = client.get("/api/recordings?page=1&page_size=2")
        data1 = response1.json()

        # 获取第二页
        response2 = client.get("/api/recordings?page=2&page_size=2")
        data2 = response2.json()

        # 验证总数一致
        assert data1["data"]["total"] == data2["data"]["total"]

        # 验证两页的录音不重复
        if len(data1["data"]["recordings"]) > 0 and len(data2["data"]["recordings"]) > 0:
            ids_page1 = {r["id"] for r in data1["data"]["recordings"]}
            ids_page2 = {r["id"] for r in data2["data"]["recordings"]}
            assert ids_page1.isdisjoint(ids_page2)
