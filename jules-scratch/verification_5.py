import asyncio
from playwright.async_api import async_playwright, expect

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # Login
            await page.goto("http://localhost:5002/login")
            await page.locator('input[name="room_number"]').fill("987")
            await page.locator('input[name="room_password"]').fill("password987")
            await page.locator('input[name="student_id"]').fill("user987")
            await page.locator('input[name="individual_password"]').fill("password987")
            await page.locator("#loginButton").click()
            await expect(page).to_have_url("http://localhost:5002/")

            # Navigate to weak problems page
            await page.goto("http://localhost:5002/weak_problems")

            # Check for the main container
            await expect(page.locator("div.container").first).to_be_visible(timeout=15000)

            # Check for the "My Weak Problems" section header
            await expect(page.get_by_role("heading", name="苦手問題一覧")).to_be_visible()
            await expect(page.locator("#my-weak-tab")).to_be_visible()

            # Check if the loading spinner disappears and the problem list appears
            # Wait for the loader to be hidden
            await expect(page.locator("#my-weak-loading")).to_be_hidden(timeout=20000)

            # After loading, check if the problem list has items
            my_problems_container = page.locator("#my-weak-problems-container")
            await expect(my_problems_container).to_be_visible()

            # Check for at least one problem card
            problem_card = my_problems_container.locator(".problem-card").first
            await expect(problem_card).to_be_visible()

            # Check content of the problem card
            await expect(problem_card.locator(".card-question")).not_to_be_empty()
            await expect(problem_card.locator(".card-answer")).to_be_hidden()

            print("✅ Verification successful: Weak problems are displayed correctly.")

        except Exception as e:
            print(f"❌ Verification failed: {e}")
            await page.screenshot(path="jules-scratch/weak_problems_error.png")
            content = await page.content()
            with open("jules-scratch/weak_problems_error.html", "w") as f:
                f.write(content)
            raise

        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())