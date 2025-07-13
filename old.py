import asyncio
import re
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError
from datetime import datetime
import time

MAX_APPLICATIONS = 4


async def accept_cookies(page):
    try:
        await page.wait_for_selector("button:has-text('Accept All')", timeout=15000)
        await page.get_by_role("button", name="Accept All").click()
        print("✅ Cookie accepted.")
        await page.screenshot(path="cookie.png", full_page=True)
    except TimeoutError:
        print("ℹ️ No cookie banner.")
    except Exception as e:
        print(f"[Cookie Error] {e}")


async def login(page):
    try:
        await page.goto("https://apps.trac.jobs/")
        await accept_cookies(page)

        print("⏳ Waiting for login form...")
        await page.wait_for_selector("input[name='FrmCoreLogin-CandidateSignIn_Email']", timeout=8000)

        print("✍️ Filling login credentials...")
        await page.fill("input[name='FrmCoreLogin-CandidateSignIn_Email']", "yusufrosemary212@gmail.com")
        await page.fill("input[name='FrmCoreLogin-CandidateSignIn_Password']", "Rose@2025")
        await page.get_by_role("button", name="Sign in").click()

        await page.wait_for_url("**/candidate/**", timeout=10000)
        print("✅ Logged in successfully.")
        

    except Exception as e:
        await page.screenshot(path="login_error.png", full_page=True)
        print(f"[Login Error] {e} — Screenshot saved to login_error.png")




async def go_to_applications(page):
    try:
        await page.get_by_role("link", name="Applications", exact=True).click()
        await page.wait_for_selector(r"#AppSearch\.Status_Draft", timeout=5000)
        await page.locator(r"#AppSearch\.Status_Draft").click()
        print("✅ Applications loaded.")
    except Exception as e:
        print(f"[Navigation Error] {e}")


async def extract_draft_links(page):
    try:
        await page.wait_for_selector("#ApplicationListResults article a", timeout=5000)
        links = page.locator("#ApplicationListResults article a", has_text="Complete your application")
        count = await links.count()

        urls = []
        for i in range(min(count, MAX_APPLICATIONS)):
            href = await links.nth(i).get_attribute("href")
            if href:
                urls.append(urljoin("https://apps.trac.jobs", href))
        print(f"🔗 Found {len(urls)} draft links.")
        return urls
    except Exception as e:
        print(f"[Draft Links Error] {e}")
        return []


async def close_toast(tab):
    try:
        await tab.wait_for_selector("button[data-bs-dismiss='toast']", timeout=3000)
        await tab.get_by_role("button", name="Close", exact=True).click()
    except:
        pass


async def fill_personal_details(tab):
    try:
        await tab.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_persdetails").click()
        checkbox = tab.locator(r"#EditAppFieldset\.personal-preferredemployment_Fulltime")
        await tab.wait_for_selector(r"#EditAppFieldset\.personal-preferredemployment_Fulltime", timeout=5000)
        if await checkbox.is_visible() and not await checkbox.is_checked():
            await checkbox.check()

        await tab.get_by_role("button", name="Save & next").wait_for(timeout=10000)
        await tab.get_by_role("button", name="Save & next").click()
        await tab.get_by_role("button", name="Save & next").click()

        await tab.wait_for_selector("#EditAppFieldset_crbquestions > div.fieldset-fields select")
        dropdowns = tab.locator("#EditAppFieldset_crbquestions > div.fieldset-fields select")
        count = await dropdowns.count()

        for i in range(count):
            options = await dropdowns.nth(i).evaluate("el => Array.from(el.options).map(o => o.value)")
            if "N" in options:
                await dropdowns.nth(i).select_option("N")

        await tab.get_by_role("button", name="Save").click()
        await close_toast(tab)
        await tab.locator("#blk_6806_ApplicationForm\\.Complete_Section_PersDetails").click()
    except Exception as e:
        print(f"[Personal Details Error] {e}")


async def fill_references(tab):
    try:
        await tab.wait_for_selector("#AppForm_Section_References > div.card-body", timeout=5000)
        await tab.locator("#AppForm_Section_References > div.card-body").click()

        await tab.wait_for_selector("#blk_6806_ApplicationForm\\.Edit_Fieldset_references", timeout=5000)
        await tab.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_references").click()

        await tab.wait_for_selector("#EditAppFieldset\\.Submit", timeout=5000)
        await tab.locator("#EditAppFieldset\\.Submit").click()

        await close_toast(tab)

        await tab.wait_for_selector("#blk_6806_ApplicationForm\\.Complete_Section_References", timeout=5000)
        await tab.locator("#blk_6806_ApplicationForm\\.Complete_Section_References").click()

    except Exception as e:
        print(f"[References Error] {e}")



async def fill_equal_opportunities(tab):
    try:
        await tab.wait_for_selector("#blk_6806_ApplicationForm\\.Edit_Fieldset_equalops", timeout=5000)
        await tab.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_equalops").click()

        await tab.wait_for_selector("button:has-text('Save & next')", timeout=5000)
        await tab.get_by_role("button", name="Save & next").click()
        await tab.get_by_role("button", name="Save & next").click()

        await tab.wait_for_selector("select[name='EditAppFieldset_source']", timeout=5000)
        await tab.select_option("select[name='EditAppFieldset_source']", "HJUK")

        await tab.wait_for_selector("button:has-text('Save & next')", timeout=5000)
        await tab.get_by_role("button", name="Save & next").click()

        await tab.wait_for_selector("input[name='EditAppFieldset_declarationb-iagree']", timeout=5000)
        await tab.locator("input[name='EditAppFieldset_declarationb-iagree']").check()

        await tab.wait_for_selector("button:has-text('Save')", timeout=5000)
        await tab.get_by_role("button", name="Save").click()

        await close_toast(tab)

        await tab.wait_for_selector("#blk_6806_ApplicationForm\\.Complete_Section_EqualOps", timeout=5000)
        await tab.locator("#blk_6806_ApplicationForm\\.Complete_Section_EqualOps").click()

    except Exception as e:
        print(f"[Equal Opps Error] {e}")

            
async def extract_job_description(tab):
    try:
        print("📰 Opening 'About this job' modal...")

        # Click the "About this job" button to open the modal
        tab.get_by_role("button", name="About this job").click()

        # Wait for the modal to appear
        tab.wait_for_selector("#VacancyDetailsModal .modal-body", timeout=5000)

        # Extract the job description content
        jd_element = tab.locator("#VacancyDetailsModal > div > div > div.modal-body > div")
        job_description = await jd_element.inner_text()

        print("✅ Job description extracted successfully.")
        print(job_description)

        # Close the modal
        tab.locator("#VacancyDetailsModal > div > div > div.modal-header > button").click()
        print("❌ Modal closed.")

        return job_description

    except Exception as e:
        print(f"[Job Description Extraction Error] {e}")
        return ""
api_key = "AIzaSyD_lPEeiygfcYVBxLHf7o_31-SeTaaQ8Cw"

import google.generativeai as genai

# Initialize Gemini API with your key
genai.configure(api_key=api_key)

async def generate_supporting_document(resume: str, job_description: str, prompt_template: str) -> str:
    if not resume.strip() or not job_description.strip():
        return "Resume and job description must not be empty."

    try:
        prompt = prompt_template.format(resume=resume, job_description=job_description)

        model = genai.GenerativeModel("gemini-2.5-pro")

        response = model.generate_content(prompt)

        return response.text
    except Exception as e:
        return f"An error occurred: {str(e)}"
    
async def handle_application(context, url, index):
    async with asyncio.Semaphore(2):  # ✅ Limit concurrent tabs (2 at a time)
        tab = await context.new_page()
        try:
            print(f"➡️ Application {index} started.")
            await tab.goto(url, timeout=45000)
            await tab.wait_for_load_state("networkidle")  # Wait for full load

            await asyncio.sleep(1.5)  # ✅ Let the UI settle

            # Process all necessary form sections
            await extract_job_description(tab)
            await asyncio.sleep(0.5)

            await fill_personal_details(tab)
            await asyncio.sleep(0.5)

            await fill_references(tab)
            await asyncio.sleep(0.5)

            await fill_equal_opportunities(tab)
            await asyncio.sleep(0.5)

            await fill_all_sections_until_supporting_info(tab)
            await asyncio.sleep(0.5)

            print(f"✅ Application {index} done.")
        except Exception as e:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_name = f"error_application_{index}_{timestamp}.png"
            await tab.screenshot(path=screenshot_name, full_page=True)
            print(f"[❌ Error in Application {index}] {e} — Screenshot: {screenshot_name}")
        finally:
            await tab.close()


async def fill_all_sections_until_supporting_info(tab):
    print("📄 Starting sequential form traversal before Supporting Info...")

    sections_to_visit = [
        "genedu",        # Education & Qualifications
        "gentraining",   # Training Courses
        "profmembership",# Professional Bodies
        "nhsservice",    # NHS Service
        "emphistory",    # Employer history
        "gaps",          # Gaps in employment
    ]

    try:
        for index, section_key in enumerate(sections_to_visit):
            section_id = f"#blk_6806_ApplicationForm\\.Edit_Fieldset_{section_key}"
            print(f"🔽 Navigating section: {section_key}")

            try:
                await tab.wait_for_selector(section_id, timeout=6000)
                await tab.locator(section_id).click()
                await asyncio.sleep(1)

                for _ in range(5):  # Attempt to press "Save & next" up to 5 times
                    try:
                        await tab.get_by_role("button", name="Save & next").click()
                        await asyncio.sleep(1)
                    except:
                        break

                # After 6th section, reload the page
                if section_key == "gaps":
                    print("🔄 Reloading page to make remaining sections visible...")
                    await tab.reload()
                    await tab.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

            except Exception as e:
                print(f"⚠️ Could not handle section {section_key}: {e}")

        print("✅ All standard sections before Supporting Info processed.\n")

    except Exception as e:
        print(f"[Traversal Error] {e}")


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            timezone_id="Europe/London"
        )

        page = await context.new_page()

        # Inject anti-detection JS
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
        """)

        success = await login(page)
        # if not success:
        #     print("❌ Stopping script: Login failed.")
        #     await context.storage_state(path="state.json")
        #     await context.close()
        #     await browser.close()
        #     return

        await go_to_applications(page)
        await context.storage_state(path="state.json")
        urls = await extract_draft_links(page)

        # Run multiple applications concurrently
        tasks = [handle_application(context, url, i + 1) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
