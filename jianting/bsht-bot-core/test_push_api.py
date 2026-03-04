"""
测试 WxPusher 推送 API
"""
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('WXPUSH_URL')
token = os.getenv('WXPUSH_TOKEN')
test_uid = "oWHb-2MyMF36laCA3z-mGjxyMSD8"

print("=" * 70)
print("测试 WxPusher 推送 API")
print("=" * 70)
print(f"URL: {url}")
print(f"Token: {token}")
print(f"测试 UID: {test_uid}")
print()

payload = {
    "token": token,
    "uid": test_uid,
    "title": "BSHT Bot 测试消息",
    "content": "这是一条测试消息"
}

print(f"发送 payload: {payload}")
print()

try:
    with httpx.Client(timeout=10) as client:
        response = client.post(url, json=payload)
        print(f"HTTP Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nJSON Response: {result}")

            if result.get('code') == 0:
                print("\n✅ 推送成功！")
            else:
                print(f"\n❌ 推送失败: {result.get('msg')}")
        else:
            print(f"\n❌ HTTP 错误: {response.status_code}")

except Exception as e:
    print(f"\n❌ 请求异常: {e}")

print("\n" + "=" * 70)
