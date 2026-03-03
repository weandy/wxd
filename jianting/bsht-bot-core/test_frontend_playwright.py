"""
BSHT Bot Web 平台 - Playwright 前端自动化测试
测试所有 7 个阶段的页面功能和用户交互
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
        await page.screenshot(path=filename)
        test_results["screenshots"].append(filename)
        print(f"  截图已保存: {filename}")
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
        print(f"[FAIL] {name} - {e}")
        return False
    except Exception as e:
        test_results["failed"] += 1
        test_results["errors"].append({"test": name, "error": str(e)})
        print(f"[ERROR] {name} - {e}")
        return False


# ==================== Page 1: 登录页面 ====================

async def test_login_page(page: Page):
    """测试登录页面"""
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")

    # 检查页面标题
    title = await page.title()
    assert "登录" in title or "Login" in title, f"页面标题错误: {title}"

    # 检查登录表单元素
    await page.wait_for_selector('input[name="username"]', timeout=5000)
    await page.wait_for_selector('input[name="password"]', timeout=5000)
    await page.wait_for_selector('button[type="submit"]', timeout=5000)

    # 尝试登录
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin123")
    await page.click('button[type="submit"]')

    # 等待跳转到仪表板
    await page.wait_for_url(f"{BASE_URL}/*", timeout=10000)
    await page.wait_for_load_state("networkidle")

    print(f"  当前URL: {page.url}")
    await take_screenshot(page, "after_login")


# ==================== Page 2: 仪表板 ====================

async def test_dashboard(page: Page):
    """测试统计仪表板"""
    await page.goto(f"{BASE_URL}/")
    await page.wait_for_load_state("networkidle")

    # 检查统计卡片
    await page.wait_for_selector('.bg-white.p-4.rounded-lg, .card', timeout=5000)

    # 检查是否有数据
    stats_text = await page.inner_text('body')
    print(f"  页面内容包含: {stats_text[:200]}...")

    await take_screenshot(page, "dashboard")


# ==================== Page 3: 录音管理 ====================

async def test_recordings_page(page: Page):
    """测试录音管理页面"""
    await page.goto(f"{BASE_URL}/recordings")
    await page.wait_for_load_state("networkidle")

    # 检查页面元素
    await page.wait_for_selector('table, .table', timeout=5000)

    # 检查筛选器
    filters = await page.query_selector_all('select, input[type="text"]')
    print(f"  找到 {len(filters)} 个筛选器")

    await take_screenshot(page, "recordings")


# ==================== Page 4: 纠错规则 ====================

async def test_rules_page(page: Page):
    """测试纠错规则管理页面"""
    await page.goto(f"{BASE_URL}/rules")
    await page.wait_for_load_state("networkidle")

    # 检查规则表格
    await page.wait_for_selector('table, .table', timeout=5000)

    # 检查添加按钮
    add_button = await page.query_selector('button:has-text("添加"), button:has-text("新建")')
    if add_button:
        print(f"  找到添加按钮")

    await take_screenshot(page, "rules")


# ==================== Page 5: 推送服务 ====================

async def test_push_page(page: Page):
    """测试推送服务管理页面"""
    await page.goto(f"{BASE_URL}/push")
    await page.wait_for_load_state("networkidle")

    # 检查页面加载
    body_text = await page.inner_text('body')
    print(f"  页面标题相关文本: {body_text[:100]}...")

    await take_screenshot(page, "push")


# ==================== Page 6: 广播任务 ====================

async def test_broadcast_page(page: Page):
    """测试广播任务管理页面"""
    await page.goto(f"{BASE_URL}/broadcast")
    await page.wait_for_load_state("networkidle")

    # 检查标签页切换
    tabs = await page.query_selector_all('[role="tab"], .tab, button')
    print(f"  找到 {len(tabs)} 个标签/按钮")

    await take_screenshot(page, "broadcast")


# ==================== Page 7: 音频库 ====================

async def test_audio_library_page(page: Page):
    """测试音频库管理页面"""
    await page.goto(f"{BASE_URL}/audio-library")
    await page.wait_for_load_state("networkidle")

    # 检查音频列表
    await page.wait_for_selector('table, .grid', timeout=5000)

    await take_screenshot(page, "audio_library")


# ==================== Page 8: 机器人监控 ====================

async def test_monitor_page(page: Page):
    """测试机器人监控页面"""
    await page.goto(f"{BASE_URL}/monitor")
    await page.wait_for_load_state("networkidle")

    # 检查资源监控卡片
    await page.wait_for_selector('.bg-white.p-4.rounded-lg, .card', timeout=5000)

    # 检查图表
    charts = await page.query_selector_all('canvas')
    print(f"  找到 {len(charts)} 个图表")

    # 检查控制按钮
    control_buttons = await page.query_selector_all('button:has-text("启动"), button:has-text("停止"), button:has-text("刷新")')
    print(f"  找到 {len(control_buttons)} 个控制按钮")

    await take_screenshot(page, "monitor")


# ==================== 交互测试 ====================

async def test_navigation(page: Page):
    """测试页面导航"""
    # 测试导航菜单
    nav_links = await page.query_selector_all('nav a, .navbar a, header a')
    print(f"  找到 {len(nav_links)} 个导航链接")

    # 点击几个主要链接测试导航
    if nav_links:
        # 点击前3个链接
        for i, link in enumerate(nav_links[:3]):
            try:
                href = await link.get_attribute('href')
                if href:
                    print(f"  导航链接 {i+1}: {href}")
            except:
                pass


async def test_responsive_design(page: Page):
    """测试响应式设计"""
    # 测试不同屏幕尺寸
    sizes = [
        {"width": 1920, "height": 1080, "name": "Desktop"},
        {"width": 768, "height": 1024, "name": "Tablet"},
        {"width": 375, "height": 667, "name": "Mobile"}
    ]

    for size in sizes:
        await page.set_viewport_size({"width": size["width"], "height": size["height"]})
        await page.wait_for_timeout(1000)
        print(f"  测试尺寸: {size['name']} ({size['width']}x{size['height']})")


# ==================== 主测试流程 ====================

async def run_all_tests():
    """运行所有前端测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - Playwright 前端自动化测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试服务器: {BASE_URL}")

    # 创建截图目录
    import os
    os.makedirs("test_screenshots", exist_ok=True)

    async with async_playwright() as p:
        # 启动浏览器（使用 Chromium）
        browser = await p.chromium.launch(
            headless=True,  # 无头模式
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()

        # 设置超时
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(10000)

        try:
            # Phase 1: 登录
            print("\n" + "="*60)
            print("Phase 1: 用户认证")
            print("="*60)
            await test("登录流程", lambda: test_login_page(page))

            # Phase 2: 仪表板
            print("\n" + "="*60)
            print("Phase 2: 统计仪表板")
            print("="*60)
            await test("仪表板页面", lambda: test_dashboard(page))
            await test("页面导航", lambda: test_navigation(page))

            # Phase 3: 录音管理
            print("\n" + "="*60)
            print("Phase 3: 录音管理")
            print("="*60)
            await test("录音管理页面", lambda: test_recordings_page(page))

            # Phase 4: 纠错规则
            print("\n" + "="*60)
            print("Phase 4: 纠错规则管理")
            print("="*60)
            await test("纠错规则页面", lambda: test_rules_page(page))

            # Phase 5: 推送服务
            print("\n" + "="*60)
            print("Phase 5: 推送服务管理")
            print("="*60)
            await test("推送服务页面", lambda: test_push_page(page))

            # Phase 6: 广播任务
            print("\n" + "="*60)
            print("Phase 6: 广播任务管理")
            print("="*60)
            await test("广播任务页面", lambda: test_broadcast_page(page))

            # Phase 7: 音频库
            print("\n" + "="*60)
            print("Phase 7: 音频库管理")
            print("="*60)
            await test("音频库页面", lambda: test_audio_library_page(page))

            # Phase 8: 机器人监控
            print("\n" + "="*60)
            print("Phase 8: 机器人监控")
            print("="*60)
            await test("监控页面", lambda: test_monitor_page(page))

            # Phase 9: 响应式设计
            print("\n" + "="*60)
            print("Phase 9: 响应式设计")
            print("="*60)
            await test("响应式布局", lambda: test_responsive_design(page))

        finally:
            await browser.close()

    # 打印测试结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"总测试数: {test_results['total']}")
    print(f"通过: {test_results['passed']} ({test_results['passed']/test_results['total']*100:.1f}%)")
    print(f"失败: {test_results['failed']} ({test_results['failed']/test_results['total']*100:.1f}%)")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"截图保存: {len(test_results['screenshots'])} 张")

    if test_results['errors']:
        print("\n失败详情:")
        for error in test_results['errors']:
            print(f"  - {error['test']}: {error['error']}")

    # 保存测试结果到 JSON
    with open("test_results_frontend.json", "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    print("\n测试结果已保存到: test_results_frontend.json")

    return test_results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
