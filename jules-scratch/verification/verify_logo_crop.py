import time
import os
from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Login
        page.goto("http://localhost:5001/login")
        page.fill('input[name="admin_username"]', "admin")
        page.fill('input[name="admin_password"]', "Avignon1309")
        page.click('button.admin-button')
        expect(page.locator("h2")).to_have_text("管理者ページ")
        print("Logged in as admin.")

        # Expand the App Info section
        page.click('div[data-bs-target="#section-app-info"]')
        print("Clicked to expand App Info section.")

        # Navigate to App Info page
        page.click('a[href="/admin/app_info"]')
        expect(page.locator("h2")).to_contain_text("アプリ情報管理")
        print("Navigated to App Info page.")

        # Select image logo type
        page.locator('input[name="logo_type"][value="image"]').check()
        print("Selected logo type 'image'.")

        # Set the file for the file input
        image_path = os.path.abspath('jules-scratch/verification/test_logo.png')
        print(f"Uploading image from: {image_path}")
        page.locator('input[name="logo_image"]').set_input_files(image_path)
        print("File set for upload.")

        # Wait for modal and cropper to appear
        expect(page.locator("#cropModal")).to_be_visible(timeout=5000)
        cropper_canvas = page.locator(".cropper-canvas")
        expect(cropper_canvas).to_be_visible(timeout=5000)
        print("Crop modal and cropper are visible.")

        page.wait_for_timeout(500)

        # Simulate a small drag on the cropper
        canvas_box = cropper_canvas.bounding_box()
        if canvas_box:
            page.mouse.move(canvas_box['x'] + 50, canvas_box['y'] + 50)
            page.mouse.down()
            page.mouse.move(canvas_box['x'] + 60, canvas_box['y'] + 60)
            page.mouse.up()
            print("Simulated cropping interaction.")
        else:
            raise Exception("Could not get bounding box for cropper canvas.")

        # Click the correct crop button
        page.click("#cropButton")
        print("Clicked '切り抜いて保存'.")

        # Wait for page to reload and check for success flash message
        expect(page.locator(".alert-success")).to_contain_text("アプリ情報を更新しました。")
        print("App info updated successfully.")

        # Verify the new logo is in the navbar
        navbar_brand = page.locator(".navbar-brand")

        expect(navbar_brand.locator("img[src*='NapoleonIcon.png']")).to_be_visible()

        logo_img = navbar_brand.locator("img[src*='uploads/logos/']")
        expect(logo_img).to_be_visible()

        navbar = page.locator("nav.navbar")
        navbar.screenshot(path="jules-scratch/verification/verification.png")
        print("Screenshot of the navbar taken.")

    except Exception as e:
        print(f"An error occurred: {e}")
        page.screenshot(path="jules-scratch/verification/error.png")
        raise
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)