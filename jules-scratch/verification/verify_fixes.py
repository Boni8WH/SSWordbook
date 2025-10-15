import re
from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Login
    page.goto("http://localhost:5000/login")
    page.locator('input[name="room_number"]').fill("101")
    page.locator('input[name="room_password"]').fill("2024101")
    page.locator('input[name="student_id"]').fill("1")
    page.locator('input[name="individual_password"]').fill("TemplarsGoldIsMine")
    page.locator("#loginButton").click()
    expect(page).to_have_url("http://localhost:5000/")

    # Verify accordion on main page
    page.goto("http://localhost:5000/")
    chapter_header = page.locator(".chapter-header").first
    chapter_item = page.locator(".chapter-item").first
    unit_list = chapter_item.locator(".unit-list")

    expect(unit_list).not_to_be_visible()
    chapter_header.click()
    expect(unit_list).to_be_visible()
    page.screenshot(path="jules-scratch/verification/accordion_verification.png")
    chapter_header.click()
    expect(unit_list).not_to_be_visible()

    # Verify weak problems page
    page.goto("http://localhost:5000/weak_problems")

    # Check personal weak problems
    page.get_by_role("button", name="個人の苦手問題").click()
    personal_list = page.locator("#personal-pane")
    expect(personal_list.get_by_text("正解: 2 / 不正解: 1")).to_be_visible()

    # Check room weak problems
    page.get_by_role("button", name="みんなの苦手問題").click()
    room_list = page.locator("#room-pane")
    # This assertion depends on the aggregated data now available
    expect(room_list.locator(".accuracy-display").first).to_contain_text(re.compile(r"正解: \d+ / 不正解: \d+"))

    page.screenshot(path="jules-scratch/verification/weak_problems_verification.png")

    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)