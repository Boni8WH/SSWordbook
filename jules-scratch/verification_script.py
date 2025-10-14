import asyncio
import os
from playwright.async_api import async_playwright, expect
import hashlib
import re
import json

# --- Configuration ---
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5002")
LOGIN_URL = f"{BASE_URL}/login"
WEAK_PROBLEMS_URL = f"{BASE_URL}/weak_problems"
SCREENSHOT_PATH = "jules-scratch/weak_problems_verification.png"

# --- Test User Credentials ---
# These should match the user created for the test
ROOM_NUMBER = "999"
ROOM_PASSWORD = "password999"
STUDENT_ID = "student999"
USERNAME = "test_weak_user"
INDIVIDUAL_PASSWORD = "password123"

# --- Expected Weak Problems ---
# These problems should be seeded in the user's history with low accuracy
# The script will check if these appear on the page.
EXPECTED_PERSONAL_WEAK_PROBLEM_Q = "三十年戦争を終結させ、主権国家体制を確立し、オランダとスイスの独立を正式に承認した国際条約を何と呼ぶか。"
EXPECTED_ROOM_WEAK_PROBLEM_Q = "三十年戦争のきっかけとなった、プロテスタント貴族の反乱が起こった神聖ローマ帝国内の地域はどこか。"

# --- Helper Functions ---
def get_problem_id(word):
    """Generates a problem ID based on word details. MUST match the Python version."""
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', '')).strip()
        answer = str(word.get('answer', '')).strip()

        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])

        return f"{chapter}-{number}-{question_clean}-{answer_clean}"
    except Exception as e:
        print(f"Error generating problem ID: {e}")
        return "error-id"

async def setup_test_data():
    """
    Creates a test user and populates their history with weak problems.
    This requires database access, so it's run via a separate script `setup_test_user.py`.
    """
    print("Setting up test data...")
    # In a real scenario, you'd use a library like `requests` or `subprocess`
    # to trigger a setup script on the server. For this example, we assume
    # the data is pre-seeded by running `setup_test_user.py`.
    # Example command:
    # process = await asyncio.create_subprocess_shell("PYTHONPATH=. python jules-scratch/setup_test_user.py")
    # await process.wait()
    # print("Test data setup complete.")
    # For now, we'll just print a message.
    print("Assuming `jules-scratch/setup_test_user.py` has been run.")


async def main():
    # await setup_test_data()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))

        try:
            print("Navigating to login page...")
            await page.goto(LOGIN_URL)

            # --- Login ---
            print("Logging in...")
            await page.fill('input[name="room_number"]', ROOM_NUMBER)
            await page.fill('input[name="room_password"]', ROOM_PASSWORD)
            await page.fill('input[name="student_id"]', STUDENT_ID)
            await page.fill('input[name="individual_password"]', INDIVIDUAL_PASSWORD)
            await page.click('button#loginButton')

            # Wait for successful login and redirect
            await page.wait_for_url(f"{BASE_URL}/")
            print("Login successful, redirected to index.")

            # --- Navigate to Weak Problems Page ---
            print(f"Navigating to {WEAK_PROBLEMS_URL}...")
            await page.goto(WEAK_PROBLEMS_URL)
            # Use the correct selector from the HTML
            await page.wait_for_selector("#personalWeakWordsContainer", timeout=15000)
            print("Weak problems page loaded.")

            # --- Verification ---
            print("Verifying content...")

            # 1. Check Personal Weak Problems
            personal_list = page.locator("#personalWeakWordsContainer")
            await expect(personal_list).to_contain_text(EXPECTED_PERSONAL_WEAK_PROBLEM_Q, timeout=10000)
            print(f"✅ Verified: Personal weak problems container contains '{EXPECTED_PERSONAL_WEAK_PROBLEM_Q}'.")

            # 2. Check Room Weak Problems
            # First, click the tab to make the room list visible
            await page.click('button#room-tab')
            room_list = page.locator("#roomWeakWordsContainer")
            await expect(room_list).to_contain_text(EXPECTED_ROOM_WEAK_PROBLEM_Q, timeout=10000)
            print(f"✅ Verified: Room weak problems container contains '{EXPECTED_ROOM_WEAK_PROBLEM_Q}'.")

            # 3. Check that Chapter Z problems are excluded from room list
            # This problem is from chapter Z in words.csv
            excluded_problem_q = "894年に遣唐使の停止を建議した人物は？"
            await expect(room_list).not_to_contain_text(excluded_problem_q, timeout=5000)
            print(f"✅ Verified: Room weak problems container does not contain excluded problem from Chapter Z.")


            # --- Screenshot ---
            print(f"Taking screenshot and saving to {SCREENSHOT_PATH}...")
            await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
            print("Screenshot saved.")

            print("\n🎉 Verification successful! All checks passed.")

        except Exception as e:
            print(f"\n❌ Verification failed: {e}")
            # On failure, take a screenshot for debugging
            failure_screenshot_path = "jules-scratch/failure_screenshot.png"
            await page.screenshot(path=failure_screenshot_path, full_page=True)
            print(f"Saved failure screenshot to {failure_screenshot_path}")
            # Re-raise the exception to ensure the script exits with a non-zero code
            raise

        finally:
            await browser.close()

if __name__ == "__main__":
    # The setup script should be run before this script
    # For now, it's a manual step.
    # To automate:
    # 1. Create setup_test_user.py
    # 2. Call it from here using asyncio.create_subprocess_shell

    # Example of how to run the setup script first:
    # os.system("PYTHONPATH=. python jules-scratch/setup_test_user.py")

    asyncio.run(main())