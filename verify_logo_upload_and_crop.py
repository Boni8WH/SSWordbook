import asyncio
from playwright.async_api import async_playwright, expect

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # 1. Navigate to the login page
            print("Navigating to login page...")
            await page.goto("http://127.0.0.1:5001/login")

            # 2. Log in as admin by filling the admin-specific form
            print("Logging in as admin...")
            await page.fill('input[id="admin_username"]', "admin")
            await page.fill('input[id="admin_password"]', "Avignon1309")
            await page.click('button.admin-button')
            await page.wait_for_url("http://127.0.0.1:5001/admin")
            print("Login successful. On admin page.")

            # 3. Expand the App Info section and navigate to settings
            print("Expanding 'App Info' section...")
            await page.click('div.section-header[data-bs-target="#section-app-info"]')

            print("Navigating to App Info settings...")
            app_info_link = page.locator('a[href="/admin/app_info"]')
            await expect(app_info_link).to_be_visible() # Wait for the link to be visible
            await app_info_link.click()

            await page.wait_for_url("http://127.0.0.1:5001/admin/app_info")
            print("On App Info page.")

            # Expect the heading to be present
            await expect(page.locator("h2:has-text('アプリ情報管理')")).to_be_visible()
            print("App Info heading is visible.")

            # 4. Select 'Image' logo type and upload an image
            print("Selecting 'Image' logo type and uploading...")
            await page.check('input[name="logo_type"][value="image"]')

            # Upload the image
            await page.set_input_files('input[name="logo_image"]', 'static/NapoleonIcon.png')
            print("Image selected for upload.")

            # Wait for the crop modal to appear
            await expect(page.locator("#cropModal")).to_be_visible(timeout=10000)
            print("Crop modal is visible.")

            # 5. Simulate cropping
            print("Simulating cropping action...")
            # Simulate a drag action on the cropper to enable the crop button
            cropper_box = await page.locator(".cropper-canvas").bounding_box()
            if cropper_box:
                await page.mouse.move(cropper_box['x'] + cropper_box['width'] / 4, cropper_box['y'] + cropper_box['height'] / 4)
                await page.mouse.down()
                await page.mouse.move(cropper_box['x'] + cropper_box['width'] * 3 / 4, cropper_box['y'] + cropper_box['height'] * 3 / 4)
                await page.mouse.up()
            else:
                raise Exception("Cropper canvas not found.")

            # Click the crop button
            await page.locator("#cropButton").click()
            print("Crop button clicked.")

            # 6. Submit the form
            print("Submitting the form...")
            await page.click('button[type="submit"]')

            # Wait for the success flash message
            await expect(page.locator("text=アプリ情報を更新しました。")).to_be_visible()
            print("Success message received.")

            # 7. Verify the logo is displayed on the top page
            print("Verifying logo on the top page...")
            await page.goto("http://127.0.0.1:5001/")

            # Find the navbar brand link
            navbar_brand = page.locator(".navbar-brand")

            # Check for the static icon first
            await expect(navbar_brand.locator("img[src*='NapoleonIcon.png']")).to_be_visible()
            print("Static Napoleon icon is visible.")

            # Check for the uploaded logo image
            uploaded_logo = navbar_brand.locator("img[src*='uploads/logos/']")
            await expect(uploaded_logo).to_be_visible()

            logo_src = await uploaded_logo.get_attribute("src")
            print(f"Uploaded logo is visible with src: {logo_src}")

            # 8. Take a screenshot for final verification
            screenshot_path = "final_verification_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to {screenshot_path}")

            print("\n✅ Verification successful! Logo uploaded, cropped, and displayed correctly.")

        except Exception as e:
            print(f"\n❌ Verification failed: {e}")
            await page.screenshot(path="verification_error.png")
            print("Saved error screenshot to verification_error.png")
            # Re-raise the exception to fail the script
            raise
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())