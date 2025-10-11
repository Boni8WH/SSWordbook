import re
import time
from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Login
        page.goto("http://localhost:5000/login")
        page.fill('input[name="room_number"]', "101")
        page.fill('input[name="room_password"]', "2024101")
        page.fill('input[name="student_id"]', "1")
        page.fill('input[name="individual_password"]', "TemplarsGoldIsMine")
        page.click('button[type="submit"]')
        page.wait_for_url("http://localhost:5000/")

        # Verify progress page
        page.goto("http://localhost:5000/progress")

        # Check that the "Weak Problems" section is gone
        weak_problems_header = page.locator("h3:has-text('苦手問題一覧')")
        expect(weak_problems_header).to_have_count(0)

        page.screenshot(path="jules-scratch/verification/progress_page.png")

        # Verify weak_problems page still works
        page.goto("http://localhost:5000/weak_problems")
        expect(page.locator("h2:has-text('苦手問題一覧')")).to_be_visible()
        page.wait_for_selector("#my-weak-problems-container:not(:empty)", timeout=15000) # Wait for cards to load
        page.screenshot(path="jules-scratch/verification/weak_problems_page.png")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        context.close()
        browser.close()

with sync_playwright() as playwright:
    run(playwright)