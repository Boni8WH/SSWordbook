import re
import json
from playwright.sync_api import sync_playwright, Page, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = browser.new_page()

    # Login
    page.goto("http://localhost:5000/login")
    page.locator("#room_number").fill("101")
    page.locator("#room_password").fill("2024101")
    page.locator("#student_id").fill("1")
    page.locator("#individual_password").fill("TemplarsGoldIsMine")
    page.locator("#loginButton").click()

    # Wait for navigation to the main page to ensure login is complete
    expect(page).to_have_url(re.compile(r"http://localhost:5000/?$"))
    page.wait_for_timeout(1000) # Wait a bit for session to be fully set

    # Directly visit the API endpoint for personal weak problems
    personal_data_response = page.goto("http://localhost:5000/api/personal_weak_problems")
    personal_data = json.loads(personal_data_response.body())
    print("Personal Weak Problems API Response:", json.dumps(personal_data, indent=2, ensure_ascii=False))

    # Directly visit the API endpoint for room weak problems
    room_data_response = page.goto("http://localhost:5000/api/room_weak_problems")
    room_data = json.loads(room_data_response.body())
    print("Room Weak Problems API Response:", json.dumps(room_data, indent=2, ensure_ascii=False))

    # Now, try to navigate to the page and take a screenshot
    page.goto("http://localhost:5000/weak_problems")
    expect(page.locator("#weakProblemsTabContent")).to_be_visible(timeout=10000)
    page.screenshot(path="jules-scratch/verification/weak_problems_personal.png")
    page.locator("#room-tab").click()
    expect(page.locator("#room-pane")).to_be_visible()
    page.screenshot(path="jules-scratch/verification/weak_problems_room.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)