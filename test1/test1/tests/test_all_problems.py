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
    page = browser.new_page(viewport={"width": 1440, "height": 950})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto("http://127.0.0.1:4173", wait_until="networkidle", timeout=60000)
    page.get_by_role("button", name="在线题库").click()
    assert page.locator(".problem-row").count() == 42

    def select_kind(label):
        page.locator(".segmented").get_by_role("button", name=label, exact=True).click()

    def solve_all_code(kind_label, expected_count):
        select_kind(kind_label)
        titles = page.locator(".problem-row .problem-name strong").all_inner_texts()
        assert len(titles) == expected_count, (kind_label, len(titles))
        for number, title in enumerate(titles, 1):
            page.locator(".problem-row").filter(has_text=title).click()
            page.get_by_role("button", name="参考答案").click()
            solution = page.locator(".solution-box pre code").inner_text()
            page.locator(".monaco-editor").wait_for(timeout=30000)
            page.wait_for_timeout(250)
            page.evaluate("value => window.__academyEditor.setValue(value)", solution)
            page.get_by_role("button", name="运行并判题").click()
            try:
                page.get_by_text("答案通过").wait_for(timeout=90000)
            except Exception:
                print(f"FAILED {kind_label} {number}/{expected_count}: {title}")
                print(page.locator(".result-content").inner_text())
                raise
            print(f"PASS {kind_label} {number}/{expected_count}: {title}")
            page.get_by_role("button", name="题库", exact=True).click()
            select_kind(kind_label)

    solve_all_code("SQL", 20)
    solve_all_code("Python", 10)

    select_kind("统计理论")
    page.locator(".problem-row").filter(has_text="COUNT如何处理NULL").click()
    page.locator(".option-list button").nth(2).click()
    page.get_by_role("button", name="提交答案").click()
    assert page.get_by_text("回答正确").is_visible()
    page.get_by_role("button", name="题库", exact=True).click()

    select_kind("业务Case")
    page.locator(".problem-row").filter(has_text="DAU突然下降15%").click()
    page.locator(".case-prompt textarea").fill("先确认指标口径和数据质量，再进行指标拆解、维度下钻、假设验证与行动复盘。")
    for checkbox in page.locator(".case-rubric input[type=checkbox]").all():
        checkbox.check()
    page.get_by_role("button", name="完成本题").click()
    assert page.get_by_text("回答与复盘已保存").is_visible()
    page.screenshot(path=str(ARTIFACTS / "expanded-case.png"), full_page=True)

    serious = [error for error in errors if "ResizeObserver" not in error]
    assert not serious, "Browser errors: " + " | ".join(serious)
    print("PASS: all 42 problems are present; all 30 code solutions execute; quiz and case interactions work")
    browser.close()
