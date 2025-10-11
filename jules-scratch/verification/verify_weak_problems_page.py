import re
from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Login
        page.goto("http://127.0.0.1:5000/login")
        page.locator('input[name="room_number"]').fill("101")
        page.locator('input[name="room_password"]').fill("2024101")
        page.locator('input[name="student_id"]').fill("1")
        page.locator('input[name="individual_password"]').fill("TemplarsGoldIsMine")
        page.locator("#loginButton").click()
        expect(page).to_have_url("http://127.0.0.1:5000/")

        # Go to the weak problems page
        page.get_by_role("link", name="苦手問題一覧").click()
        expect(page).to_have_url("http://127.0.0.1:5000/weak_problems")

        # Wait for "Your Weak Problems" to load and take screenshot
        expect(page.locator("#my-weak-problems-container .problem-card")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/your_weak_problems.png")

        # Go to "Everyone's Weak Problems"
        page.get_by_role("button", name="みんなの苦手問題 Top 20").click()

        # Wait for "Everyone's Weak Problems" to load and take screenshot
        expect(page.locator("#everyone-weak-problems-container .problem-card")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/everyone_weak_problems.png")

        print("Verification successful!")

    except Exception as e:
        print(f"An error occurred: {e}")
        page.screenshot(path="jules-scratch/verification/error.png")

    finally:
        browser.close()

with sync_playwright() as p:
    run(p)