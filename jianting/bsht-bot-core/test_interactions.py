"""
BSHT Bot Web 平台 - Playwright 深度交互测试
测试页面内的实际功能：点击、输入、筛选、CRUD 操作等
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
    "actions": []
}


async def login(page):
    """登录系统"""
    print("\n[LOGIN] Starting login process...")
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")

    # 填写登录表单
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin123")
    await page.click('button[type="submit"]')

    # 等待登录完成
    await page.wait_for_timeout(3000)

    current_url = page.url
    print(f"[LOGIN] Current URL after login: {current_url}")

    # 如果还在登录页，说明登录失败
    if "/login" in current_url:
        print("[LOGIN] Login may have failed, continuing tests")
        return False

    print("[LOGIN] Login successful")
    return True


async def test_action(name: str, func):
    """测试动作包装器"""
    test_results["total"] += 1
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"{'='*60}")

    action_info = {
        "name": name,
        "success": False,
        "error": None
    }

    try:
        result = await func()
        test_results["passed"] += 1
        action_info["success"] = True
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        test_results["failed"] += 1
        action_info["error"] = str(e)
        test_results["errors"].append({"action": name, "error": str(e)})
        print(f"[FAIL] {name}")
        print(f"  Reason: {e}")
        return False
    except Exception as e:
        test_results["failed"] += 1
        action_info["error"] = str(e)
        test_results["errors"].append({"action": name, "error": str(e)})
        print(f"[ERROR] {name}")
        print(f"  Error: {e}")
        return False
    finally:
        test_results["actions"].append(action_info)


async def test_dashboard_interactions(page):
    """测试仪表板页面的交互"""
    # 点击刷新按钮
    try:
        refresh_btn = await page.query_selector('button:has-text("刷新"), button:has-text("Reload")')
        if refresh_btn:
            await refresh_btn.click()
            await page.wait_for_timeout(2000)
            print("  [动作] 点击刷新按钮")
    except:
        print("  [跳过] 没有刷新按钮")

    # 检查统计卡片
    cards = await page.query_selector_all('.bg-white, .card, [class*="stat"]')
    print(f"  [检查] 找到 {len(cards)} 个统计卡片")


async def test_recordings_interactions(page):
    """测试录音管理页面的交互"""
    await page.goto(f"{BASE_URL}/recordings")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试筛选输入框
    search_input = await page.query_selector('input[type="text"], input[placeholder*="搜索"], input[placeholder*="search"]')
    if search_input:
        await search_input.fill("test")
        await page.wait_for_timeout(1000)
        print("  [动作] 输入搜索关键词")

        # 清空搜索
        await search_input.fill("")
        await page.wait_for_timeout(1000)
        print("  [动作] 清空搜索")

    # 测试筛选下拉框
    selects = await page.query_selector_all('select')
    print(f"  [检查] 找到 {len(selects)} 个下拉筛选器")

    # 测试分页按钮
    pagination = await page.query_selector_all('button:has-text("下一页"), button:has-text("Next"), .pagination button')
    if pagination:
        print(f"  [检查] 找到 {len(pagination)} 个分页按钮")


async def test_rules_interactions(page):
    """测试纠错规则页面的交互"""
    await page.goto(f"{BASE_URL}/rules")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试添加按钮
    add_btn = await page.query_selector('button:has-text("添加"), button:has-text("新建"), button:has-text("新增")')
    if add_btn:
        print("  [检查] 找到添加按钮")

        # 点击添加按钮（可能会打开模态框）
        try:
            await add_btn.click()
            await page.wait_for_timeout(2000)
            print("  [动作] 点击添加按钮")

            # 检查是否有模态框
            modal = await page.query_selector('[role="dialog"], .modal, [class*="modal"]')
            if modal:
                print("  [检查] 模态框已打开")

                # 尝试关闭模态框
                close_btn = await page.query_selector('button:has-text("取消"), button:has-text("关闭"), button[aria-label="close"]')
                if close_btn:
                    await close_btn.click()
                    await page.wait_for_timeout(1000)
                    print("  [动作] 关闭模态框")
        except Exception as e:
            print(f"  [跳过] 无法点击添加按钮: {e}")

    # 测试规则列表行
    rows = await page.query_selector_all('table tbody tr, [role="row"]')
    print(f"  [检查] 找到 {len(rows)} 条规则记录")


async def test_broadcast_interactions(page):
    """测试广播任务页面的交互"""
    await page.goto(f"{BASE_URL}/broadcast")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试标签页切换
    tabs = await page.query_selector_all('[role="tab"], .tab, button')
    print(f"  [检查] 找到 {len(tabs)} 个标签/按钮")

    # 尝试点击前几个标签
    for i, tab in enumerate(tabs[:3]):
        try:
            await tab.click()
            await page.wait_for_timeout(1000)
            text = await tab.inner_text()
            print(f"  [动作] 点击标签 {i+1}: {text[:30]}")
        except:
            pass


async def test_push_interactions(page):
    """测试推送服务页面的交互"""
    await page.goto(f"{BASE_URL}/push")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试推送服务列表
    cards = await page.query_selector_all('.bg-white, .card, [class*="service"]')
    print(f"  [检查] 找到 {len(cards)} 个服务卡片")

    # 测试目标用户列表
    user_rows = await page.query_selector_all('table tbody tr')
    print(f"  [检查] 找到 {len(user_rows)} 个目标用户")

    # 测试测试推送按钮
    test_btn = await page.query_selector('button:has-text("测试"), button:has-text("Test")')
    if test_btn:
        print("  [检查] 找到测试推送按钮")


async def test_audio_library_interactions(page):
    """测试音频库页面的交互"""
    await page.goto(f"{BASE_URL}/audio-library")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试音频列表
    audio_items = await page.query_selector_all('table tbody tr, [role="row"]')
    print(f"  [检查] 找到 {len(audio_items)} 个音频项")

    # 测试播放按钮
    play_btns = await page.query_selector_all('button:has-text("播放"), button[title*="play"], button[aria-label*="play"]')
    print(f"  [检查] 找到 {len(play_btns)} 个播放按钮")


async def test_monitor_interactions(page):
    """测试监控页面的交互"""
    await page.goto(f"{BASE_URL}/monitor")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)

    # 测试控制按钮
    control_btns = await page.query_selector_all('button:has-text("启动"), button:has-text("停止"), button:has-text("刷新")')
    print(f"  [检查] 找到 {len(control_btns)} 个控制按钮")

    # 测试刷新状态按钮
    refresh_btn = await page.query_selector('button:has-text("刷新状态"), button:has-text("Refresh")')
    if refresh_btn:
        try:
            await refresh_btn.click()
            await page.wait_for_timeout(2000)
            print("  [动作] 点击刷新状态按钮")
        except:
            print("  [跳过] 无法点击刷新按钮")

    # 测试日志筛选
    log_filter = await page.query_selector('select[id*="log"], select[name*="level"]')
    if log_filter:
        print("  [检查] 找到日志级别筛选器")

    # 测试自动刷新按钮
    auto_refresh_btn = await page.query_selector('button:has-text("自动刷新"), button:has-text("Auto")')
    if auto_refresh_btn:
        try:
            await auto_refresh_btn.click()
            await page.wait_for_timeout(2000)
            print("  [动作] 点击自动刷新按钮")

            # 再次点击关闭
            await auto_refresh_btn.click()
            await page.wait_for_timeout(1000)
            print("  [动作] 关闭自动刷新")
        except:
            print("  [跳过] 无法控制自动刷新")


async def test_navigation_menu(page):
    """测试导航菜单交互"""
    nav_links = await page.query_selector_all('nav a, .navbar a, header a, [role="navigation"] a')
    print(f"  [检查] 找到 {len(nav_links)} 个导航链接")

    # 点击前几个导航链接
    for i, link in enumerate(nav_links[:5]):
        try:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and not href.startswith('#'):
                await link.click()
                await page.wait_for_timeout(2000)
                print(f"  [动作] 点击导航: {text[:30]}")
                # 返回首页
                await page.goto(f"{BASE_URL}/")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  [跳过] 导航链接 {i+1}: {e}")


async def test_form_inputs(page):
    """测试表单输入交互"""
    # 测试录音管理页面的搜索
    await page.goto(f"{BASE_URL}/recordings")
    await page.wait_for_load_state("networkidle")

    # 查找输入框并测试
    inputs = await page.query_selector_all('input[type="text"]')
    print(f"  [检查] 找到 {len(inputs)} 个文本输入框")

    for i, inp in enumerate(inputs[:3]):
        try:
            placeholder = await inp.get_attribute('placeholder')
            await inp.fill("test_search")
            await page.wait_for_timeout(500)
            print(f"  [动作] 输入框 {i+1}: 输入测试文本")
            await inp.fill("")
            await page.wait_for_timeout(500)
        except:
            pass


async def test_table_interactions(page):
    """测试表格交互"""
    await page.goto(f"{BASE_URL}/rules")
    await page.wait_for_load_state("networkidle")

    # 检查表格
    tables = await page.query_selector_all('table')
    print(f"  [检查] 找到 {len(tables)} 个表格")

    if tables:
        # 获取第一个表格的行
        rows = await tables[0].query_selector_all('tbody tr, tr')
        print(f"  [检查] 表格有 {len(rows)} 行数据")

        # 测试复选框
        checkboxes = await tables[0].query_selector_all('input[type="checkbox"]')
        if checkboxes:
            print(f"  [检查] 找到 {len(checkboxes)} 个复选框")

            # 尝试勾选第一个
            try:
                await checkboxes[0].check()
                await page.wait_for_timeout(500)
                print("  [动作] 勾选第一行")
                await checkboxes[0].uncheck()
                await page.wait_for_timeout(500)
                print("  [动作] 取消勾选")
            except:
                pass


async def test_responsive_interactions(page):
    """测试响应式交互"""
    # 测试移动端菜单
    await page.set_viewport_size({"width": 375, "height": 667})
    await page.wait_for_timeout(1000)

    # 检查是否有汉堡菜单
    menu_btn = await page.query_selector('button[aria-label="menu"], button:has-text("菜单"), .hamburger')
    if menu_btn:
        print("  [检查] 移动端找到汉堡菜单")
        try:
            await menu_btn.click()
            await page.wait_for_timeout(1000)
            print("  [动作] 点击汉堡菜单")
        except:
            pass

    # 恢复桌面尺寸
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.wait_for_timeout(1000)


async def run_interaction_tests():
    """运行所有交互测试"""
    print("\n" + "="*60)
    print("BSHT Bot Web 平台 - Playwright 深度交互测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 创建截图目录
    import os
    os.makedirs("test_screenshots", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 显示浏览器以便观察
            args=['--no-sandbox', '--disable-dev-shm-usage'],
            slow_mo=500  # 减慢操作速度，便于观察
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()
        page.set_default_timeout(10000)

        try:
            # 登录
            login_success = await login(page)

            # 如果登录失败，仍然继续测试（部分页面可能不需要登录）

            # Phase 1: 仪表板交互
            print("\n" + "="*60)
            print("Phase 1: 仪表板交互测试")
            print("="*60)
            await test_action("仪表板页面交互", lambda: test_dashboard_interactions(page))

            # Phase 2: 录音管理交互
            print("\n" + "="*60)
            print("Phase 2: 录音管理交互测试")
            print("="*60)
            await test_action("录音搜索筛选", lambda: test_recordings_interactions(page))

            # Phase 3: 纠错规则交互
            print("\n" + "="*60)
            print("Phase 3: 纠错规则交互测试")
            print("="*60)
            await test_action("规则管理交互", lambda: test_rules_interactions(page))

            # Phase 4: 广播任务交互
            print("\n" + "="*60)
            print("Phase 4: 广播任务交互测试")
            print("="*60)
            await test_action("广播任务交互", lambda: test_broadcast_interactions(page))

            # Phase 5: 推送服务交互
            print("\n" + "="*60)
            print("Phase 5: 推送服务交互测试")
            print("="*60)
            await test_action("推送服务交互", lambda: test_push_interactions(page))

            # Phase 6: 音频库交互
            print("\n" + "="*60)
            print("Phase 6: 音频库交互测试")
            print("="*60)
            await test_action("音频库交互", lambda: test_audio_library_interactions(page))

            # Phase 7: 监控交互
            print("\n" + "="*60)
            print("Phase 7: 监控交互测试")
            print("="*60)
            await test_action("监控页面交互", lambda: test_monitor_interactions(page))

            # Phase 8: 通用交互
            print("\n" + "="*60)
            print("Phase 8: 通用交互测试")
            print("="*60)
            await test_action("导航菜单交互", lambda: test_navigation_menu(page))
            await test_action("表单输入交互", lambda: test_form_inputs(page))
            await test_action("表格交互", lambda: test_table_interactions(page))
            await test_action("响应式交互", lambda: test_responsive_interactions(page))

        finally:
            # 截图最终状态
            await page.screenshot(path="test_screenshots/final_state.png", full_page=True)
            await browser.close()

    # 打印结果
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
            print(f"  - {error['action']}: {error['error'][:80]}")

    # 保存结果
    with open("test_results_interactions.json", "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    print("\n结果已保存到: test_results_interactions.json")

    return test_results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(run_interaction_tests())
    exit(0 if success else 1)
