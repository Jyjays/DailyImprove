import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda message: print("BROWSER:", message.text) if "python-runner" in message.text else None)
    page.goto("http://127.0.0.1:4173", wait_until="networkidle", timeout=60000)

    assert page.get_by_text("把每一次查询").is_visible()
    assert page.get_by_text("今日训练").is_visible()
    page.screenshot(path=str(ARTIFACTS / "dashboard.png"), full_page=True)

    page.get_by_role("button", name="知识路线").click()
    assert page.get_by_role("heading", name="八周知识路线").is_visible()
    assert page.locator(".module-card").count() == 8
    page.get_by_role("button", name="查询、筛选与聚合").click()
    assert page.get_by_role("heading", name="查询、筛选与聚合", exact=True).is_visible()
    page.get_by_role("button", name="标记为已完成").click()
    assert page.get_by_role("button", name="已完成本节").is_visible()

    page.get_by_role("button", name="在线题库").click()
    assert page.get_by_role("heading", name="在线题库").is_visible()
    page.get_by_role("button", name="渠道注册用户数").click()
    page.get_by_role("button", name="参考答案").click()
    solution = page.locator(".solution-box pre code").inner_text()
    page.wait_for_function("window.__academyEditor !== undefined")
    page.evaluate("value => window.__academyEditor.setValue(value)", solution)
    page.get_by_role("button", name="运行并判题").click()
    try:
        page.get_by_text("答案通过").wait_for(timeout=60000)
    except Exception:
        page.screenshot(path=str(ARTIFACTS / "sql-failure.png"), full_page=True)
        print("RESULT DEBUG:", page.locator(".result-content").inner_text())
        print("EDITOR DEBUG:", page.locator(".monaco-editor .view-lines").inner_text())
        raise
    assert page.get_by_text("答案通过").is_visible()
    page.screenshot(path=str(ARTIFACTS / "sql-passed.png"), full_page=True)

    page.get_by_role("button", name="题库", exact=True).click()
    page.locator(".segmented").get_by_role("button", name="Python", exact=True).click()
    page.get_by_role("button", name="清洗订单数据").click()
    page.get_by_role("button", name="参考答案").click()
    py_solution = page.locator(".solution-box pre code").inner_text()
    page.wait_for_function("window.__academyEditor !== undefined")
    page.evaluate("value => window.__academyEditor.setValue(value)", py_solution)
    page.get_by_role("button", name="运行并判题").click()
    try:
        page.get_by_text("答案通过").wait_for(timeout=75000)
    except Exception:
        page.screenshot(path=str(ARTIFACTS / "python-failure.png"), full_page=True)
        print("PYTHON RESULT DEBUG:", page.locator(".result-content").inner_text())
        raise
    assert page.get_by_text("4项测试全部通过").is_visible()
    page.screenshot(path=str(ARTIFACTS / "python-passed.png"), full_page=True)

    serious = [error for error in errors if "ResizeObserver" not in error]
    assert not serious, "Browser errors: " + " | ".join(serious)
    print("PASS: dashboard, curriculum, progress, SQL/Python execution and grading")
    browser.close()
