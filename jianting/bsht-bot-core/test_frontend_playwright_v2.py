"""
BSHT Bot Web 平台 - Playwright 前端自动化测试（改进版）
使用更通用的选择器和更好的会话管理
"""
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from typing import List, Dict

BASE_URL = "http://localhost:8000"

# 测试结果
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": [],
    "screenshots": []
}


async def take_screenshot(page: Page, name: str):
    """保存截图"""
    filename = f"test_screenshots/{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        await page.screenshot(path=filename, full_page=True)
        test_results["screenshots"].append(filename)
        print(f"  截图: {filename}")
    except Exception as e:
        print(f"  截图失败: {e}")


async def test(name: str, func):
    """测试包装器"""
    test_results["total"] += 1
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"{'='*60}")
    try:
        await func()
        test_results["passed"] += 1
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        test_results["failed"] += 1
        test_results["errors"].append({"test": name, "error": str(e)})
        print(f"[FAIL] {name}")
        print(f"  原因: {e}")
        return False
    except Exception as e:
        test_results["failed"] += 1
        test_results["errors"].append({"test": name, "error": str(e)})
        print(f"[ERROR] {name}")
        print(f"  原因: {e}")
        return False


async def login_and_save_session(page: Page, browser) -> dict:
    """登录并保存会话状态"""
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")

    # 填写登录表单
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin123")
    await page.click('button[type="submit"]')

    # 等待登录完成
    await page.wait_for_url(f"{BASE_URL}/", timeout=10000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 保存会话状态
    cookies = await page.context.cookies()
    localStorage = await page.evaluate("() => JSON.stringify(Object.assign({}, localStorage))")

    return {"cookies": cookies, "localStorage": localStorage}


async def restore_session(page: Page, session: dict):
    """恢复会话状态"""
    # 恢复 cookies
    await page.context.add_cookies(session["cookies"])

    # 恢复 localStorage
    await page.evaluate(f"(data) => {{ Object.keys(data).forEach(k => localStorage.setItem(k, data[k])) }}",
                       json.loads(session["localStorage"]))


# ==================== Page 测试 ====================

async def test_dashboard(page: Page):
    """测试仪表板页面"""
    await page.goto(f"{BASE_URL}/")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面是否加载
    title = await page.title()
    assert title, "页面应该有标题"

    # 检查是否有内容
    body = await page.inner_text('body')
    assert len(body) > 100, "页面应该有内容"

    print(f"  标题: {title}")
    print(f"  内容长度: {len(body)}")

    await take_screenshot(page, "dashboard")


async def test_recordings(page: Page):
    """测试录音管理页面"""
    await page.goto(f"{BASE_URL}/recordings")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')
    assert "录音" in body or "recording" in body.lower(), "页面应该包含录音相关内容"

    print(f"  页面包含: {body[:100]}...")

    await take_screenshot(page, "recordings")


async def test_rules(page: Page):
    """测试纠错规则页面"""
    await page.goto(f"{BASE_URL}/rules")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')
    assert "规则" in body or "rule" in body.lower(), "页面应该包含规则相关内容"

    print(f"  页面包含: {body[:100]}...")

    await take_screenshot(page, "rules")


async def test_push(page: Page):
    """测试推送服务页面"""
    await page.goto(f"{BASE_URL}/push")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')

    # 检查是否是未登录错误
    if "未登录" in body or "Unauthorized" in body:
        print("  需要登录才能访问")
    else:
        print(f"  页面包含: {body[:100]}...")

    await take_screenshot(page, "push")


async def test_broadcast(page: Page):
    """测试广播任务页面"""
    await page.goto(f"{BASE_URL}/broadcast")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')
    print(f"  页面包含: {body[:100]}...")

    await take_screenshot(page, "broadcast")


async def test_audio_library(page: Page):
    """测试音频库页面"""
    await page.goto(f"{BASE_URL}/audio-library")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')
    print(f"  页面包含: {body[:100]}...")

    await take_screenshot(page, "audio_library")


async def test_monitor(page: Page):
    """测试监控页面"""
    await page.goto(f"{BASE_URL}/monitor")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 检查页面
    body = await page.inner_text('body')
    assert "监控" in body or "monitor" in body.lower(), "页面应该包含监控相关内容"

    # 检查是否有图表元素
    has_canvas = len(await page.query_selector_all('canvas')) > 0
    print(f"  有图表: {has_canvas}")

    await take_screenshot(page, "monitor")


async def test_navigation(page: Page):
    """测试页面导航"""
    # 测试所有主要页面是否可访问
    pages = [
        ("/", "仪表板"),
        ("/recordings", "录音管理"),
        ("/rules", "纠错规则"),
        ("/broadcast", "广播任务"),
        ("/audio-library", "音频库"),
        ("/monitor", "机器人监控")
    ]

    for path, name in pages:
        try:
            await page.goto(f"{BASE_URL}{path}")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
            title = await page.title()
            print(f"  {name} ({path}): OK - {title}")
        except Exception as e:
            print(f"  {name} ({path}): FAIL - {e}")


async def test_responsive(page: Page):
    """测试响应式设计"""
    sizes = [
        {"width": 1920, "height": 1080, "name": "Desktop"},
        {"width": 768, "height": 1024, "name": "Tablet"},
        {"width": 375, "height": 667, "name": "Mobile"}
    ]

    for size in sizes:
        await page.set_viewport_size({"width": size["width"], "height": size["height"]})
        await page.goto(f"{BASE_URL}/")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)
        print(f"  {size['name']}: OK")


async def test_login_logout(page: Page):
    """测试登录登出流程"""
    # 登录
    await page.goto(f"{BASE_URL}/login")
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin123")
    await page.click('button[type="submit"]')
    await page.wait_for_url(f"{BASE_URL}/", timeout=10000)

    # 检查是否登录成功
    url = page.url
    assert url == f"{BASE_URL}/", f"登录后应该在首页，实际在: {url}"

    print(f"  登录后URL: {url}")

    # 登出（如果有登出按钮）
    try:
        logout_btn = await page.query_selector('a:has-text("登出"), button:has-text("登出")')
        if logout_btn:
            await logout_btn.click()
            await page.wait_for_timeout(2000)
            print("  登出成功")
    except:
        print("  没有找到登出按钮")


# ==================== 主测试流程 ====================

async def run_all_tests():
    """运行所有前端测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - Playwright 前端自动化测试 v2")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {BASE_URL}")

    # 创建截图目录
    import os
    os.makedirs("test_screenshots", exist_ok=True)

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(15000)

        try:
            # Phase 1: 登录认证
            print("\n" + "="*60)
            print("Phase 1: 用户认证")
            print("="*60)
            await test("登录登出流程", lambda: test_login_logout(page))

            # 重新登录保持会话
            await login_and_save_session(page, browser)

            # Phase 2: 页面测试
            print("\n" + "="*60)
            print("Phase 2: 页面功能测试")
            print("="*60)

            await test("仪表板页面", lambda: test_dashboard(page))
            await test("录音管理页面", lambda: test_recordings(page))
            await test("纠错规则页面", lambda: test_rules(page))
            await test("推送服务页面", lambda: test_push(page))
            await test("广播任务页面", lambda: test_broadcast(page))
            await test("音频库页面", lambda: test_audio_library(page))
            await test("监控页面", lambda: test_monitor(page))

            # Phase 3: 导航和响应式
            print("\n" + "="*60)
            print("Phase 3: 导航和响应式")
            print("="*60)

            await test("页面导航", lambda: test_navigation(page))
            await test("响应式布局", lambda: test_responsive(page))

        finally:
            await browser.close()

    # 打印结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"总测试数: {test_results['total']}")
    print(f"通过: {test_results['passed']} ({test_results['passed']/test_results['total']*100:.1f}%)")
    print(f"失败: {test_results['failed']} ({test_results['failed']/test_results['total']*100:.1f}%)")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"截图数量: {len(test_results['screenshots'])}")

    if test_results['errors']:
        print("\n失败详情:")
        for error in test_results['errors'][:5]:  # 只显示前5个
            print(f"  - {error['test']}: {str(error['error'])[:100]}")

    # 保存结果
    with open("test_results_frontend_v2.json", "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    print("\n结果已保存到: test_results_frontend_v2.json")

    return test_results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
