"""
BSHT Bot Web 平台 - Playwright 简化前端测试
测试所有页面的可访问性和基本元素
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8000"

test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": [],
    "pages": []
}


async def test_page(browser, url: str, name: str):
    """测试单个页面"""
    test_results["total"] += 1
    print(f"\n测试: {name}")
    print(f"URL: {url}")

    page = await browser.new_page()
    page_info = {
        "name": name,
        "url": url,
        "success": False,
        "title": "",
        "elements": 0,
        "error": None
    }

    try:
        # 访问页面
        await page.goto(url, wait_until="networkidle", timeout=15000)

        # 获取页面标题
        title = await page.title()
        page_info["title"] = title

        # 检查页面内容
        body_text = await page.inner_text('body')
        page_info["elements"] = len(body_text)

        # 检查是否有错误信息
        if "404" in body_text or "Not Found" in body_text:
            raise Exception("页面返回 404")

        if "500" in body_text or "Internal Server Error" in body_text:
            raise Exception("页面返回 500")

        # 截图
        filename = f"test_screenshots/{name.replace(' ', '_')}_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=filename, full_page=True)

        test_results["passed"] += 1
        page_info["success"] = True
        print(f"  [OK] 标题: {title}")
        print(f"  [OK] 内容长度: {len(body_text)}")
        print(f"  [OK] 截图: {filename}")

    except Exception as e:
        test_results["failed"] += 1
        test_results["errors"].append({"page": name, "error": str(e)})
        page_info["error"] = str(e)
        print(f"  [FAIL] {e}")

    finally:
        await page.close()
        test_results["pages"].append(page_info)

    return page_info["success"]


async def run_tests():
    """运行所有页面测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - Playwright 页面测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 创建截图目录
    import os
    os.makedirs("test_screenshots", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        try:
            # 测试所有页面
            pages = [
                (f"{BASE_URL}/", "首页-仪表板"),
                (f"{BASE_URL}/login", "登录页"),
                (f"{BASE_URL}/recordings", "录音管理"),
                (f"{BASE_URL}/rules", "纠错规则"),
                (f"{BASE_URL}/push", "推送服务"),
                (f"{BASE_URL}/broadcast", "广播任务"),
                (f"{BASE_URL}/audio-library", "音频库"),
                (f"{BASE_URL}/monitor", "机器人监控"),
                (f"{BASE_URL}/health", "健康检查"),
                (f"{BASE_URL}/docs", "API 文档")
            ]

            for url, name in pages:
                await test_page(browser, url, name)

        finally:
            await browser.close()

    # 打印结果
    print("\n" + "="*60)
    print("测试结果")
    print("="*60)
    print(f"总测试: {test_results['total']}")
    print(f"通过: {test_results['passed']} ({test_results['passed']/test_results['total']*100:.1f}%)")
    print(f"失败: {test_results['failed']} ({test_results['failed']/test_results['total']*100:.1f}%)")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 页面详情
    print("\n页面测试详情:")
    for page_info in test_results["pages"]:
        status = "[OK]" if page_info["success"] else "[FAIL]"
        print(f"  {status} {page_info['name']}")
        if page_info["success"]:
            print(f"       标题: {page_info['title']}")
            print(f"       内容: {page_info['elements']} 字符")
        else:
            print(f"       错误: {page_info['error']}")

    # 保存结果
    with open("test_results_pages.json", "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)

    print("\n结果已保存到: test_results_pages.json")
    return test_results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)
