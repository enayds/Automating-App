import PySimpleGUI as sg
import asyncio
import threading
import time

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

status_dict = {}
remaining_drafts = 0
lock = threading.Lock()

DRAFT_LIMIT_PER_BATCH = 5

def update_status(app_id, status):
    with lock:
        status_dict[app_id] = status

# function to handle cookies 
async def accept_cookies(page, app_id):
    try:
        update_status(app_id, "Checking for cookie banner")
        await page.wait_for_selector("button:has-text('Accept All')", timeout=3000)
        await page.get_by_role("button", name="Accept All").click()
        update_status(app_id, "Cookie banner accepted")
    except PlaywrightTimeoutError:
        update_status(app_id, "No cookie banner found")
    except Exception as e:
        update_status(app_id, f"Cookie error: {str(e)}")

# function to handle login
async def login(page, email, password, app_id):
    try:
        update_status(app_id, "Navigating to login page")
        await page.goto("https://apps.trac.jobs/")
        await accept_cookies(page, app_id)

        update_status(app_id, "Filling in login form")
        await page.wait_for_selector("input[name='FrmCoreLogin-CandidateSignIn_Email']", timeout=8000)
        await page.fill("input[name='FrmCoreLogin-CandidateSignIn_Email']", email)
        await page.fill("input[name='FrmCoreLogin-CandidateSignIn_Password']", password)
        await page.get_by_role("button", name="Sign in").click()

        update_status(app_id, "Waiting for dashboard")
        await page.wait_for_url("https://apps.trac.jobs/dashboard", timeout=10000)

        return True
    except Exception as e:
        update_status(app_id, f"Login error: {str(e)}")
        return False

# function to run automation
async def run_automation(email, password):
    app_id = "Application"
    update_status(app_id, "Starting automation")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            login_success = await login(page, email, password, app_id)
            if not login_success:
                update_status(app_id, "Login failed. Aborting.")
                return

            draft_urls = await navigate_and_get_drafts(page, app_id)
            if not draft_urls:
                update_status(app_id, "No drafts found. Exiting.")
                return

            await apply_to_drafts_in_batches(context, draft_urls, app_id)

            await context.close()
            await browser.close()
            update_status(app_id, "Automation completed")

    except Exception as e:
        update_status(app_id, f"[Automation Error] {str(e)}")

# function to handle closing toast popup
async def close_toast(page, app_id):
    try:
        await page.wait_for_selector("button[data-bs-dismiss='toast']", timeout=3000)
        await page.get_by_role("button", name="Close", exact=True).click()
        update_status(app_id, "Toast closed")
    except:
        pass

# function to handle draft applications 
async def handle_draft_application(page, url, app_id):
    try:
        update_status(app_id, f"Opening: {url}")
        await page.goto(url)
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Section functions
        await extract_job_description(page, app_id)

        # await fill_personal_details(page, app_id)
        # await fill_references(page, app_id)
        await fill_equal_opportunities(page, app_id)

        update_status(app_id, f"✅ Done: {url}")
    except Exception as e:
        update_status(app_id, f"[Draft Error] {url}: {str(e)}")
    finally:
        await page.close()

# function that handle batches of draft
async def apply_to_drafts_in_batches(context, draft_urls, app_id):
    global remaining_drafts

    try:
        for i in range(0, len(draft_urls), DRAFT_LIMIT_PER_BATCH):
            batch = draft_urls[i:i + DRAFT_LIMIT_PER_BATCH]
            update_status(app_id, f"Processing batch of {len(batch)} drafts")

            tasks = []

            for url in batch:
                page = await context.new_page()
                task = asyncio.create_task(handle_draft_application(page, url, app_id))
                tasks.append(task)

            await asyncio.gather(*tasks)

            remaining_drafts -= len(batch)
            update_status(app_id, f"{remaining_drafts} drafts remaining")

    except Exception as e:
        update_status(app_id, f"[Batch Error] {str(e)}")

# function to handle navigation
async def navigate_and_get_drafts(page, app_id):
    try:
        base_url = "https://apps.trac.jobs/applicationlist?Text=&Status%5B%5D=Draft&Submit=Search&_srt=lastupdateforcandidate&_sd=d&_pg="
        draft_urls = []
        page_number = 1

        update_status(app_id, "Navigating to Applications")
        await page.get_by_role("link", name="Applications", exact=True).click()

        await page.wait_for_selector("#AppSearch\\.Status_Draft", timeout=5000)
        await page.locator("#AppSearch\\.Status_Draft").click()
        await page.wait_for_timeout(2000)

        while True:
            paginated_url = f"{base_url}{page_number}"
            await page.goto(paginated_url)
            await page.wait_for_timeout(2000)

            try:
                await page.wait_for_selector("#ApplicationListResults article a", timeout=5000)
                links = page.locator("#ApplicationListResults article a", has_text="Complete your application")
                count = await links.count()
                if count == 0:
                    break

                for i in range(count):
                    href = await links.nth(i).get_attribute("href")
                    if href:
                        full_url = "https://apps.trac.jobs" + href if href.startswith("/") else href
                        draft_urls.append(full_url)

                update_status(app_id, f"Page {page_number}: Collected {count}, Total: {len(draft_urls)}")

                if count < 10:
                    break  # last page
                page_number += 1

            except Exception as e:
                update_status(app_id, f"Error on page {page_number}: {str(e)}")
                break

        global remaining_drafts
        remaining_drafts = len(draft_urls)
        return draft_urls

    except Exception as e:
        update_status(app_id, f"[Draft Collection Error] {str(e)}")
        return []

# function to extract job description
async def extract_job_description(page, app_id):
    try:
        update_status(app_id, "[Job Desc] Opening modal")
        await page.get_by_role("button", name="About this job").click()
        await page.wait_for_selector("#VacancyDetailsModal .modal-body", timeout=5000)

        jd_element = page.locator("#VacancyDetailsModal > div > div > div.modal-body > div")
        job_description = await jd_element.inner_text()

        update_status(app_id, "[Job Desc] Extracted successfully")
        await page.locator("#VacancyDetailsModal > div > div > div.modal-header > button").click()

        return job_description

    except Exception as e:
        update_status(app_id, f"[Job Desc Error] {str(e)}")
        return ""

# function to fill personal information
async def fill_personal_details(page, app_id):
    try:
        update_status(app_id, "[Personal] Starting section")
        step_marker = "start"

        for attempt in range(2):
            try:
                if step_marker == "start":
                    await page.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_persdetails").click()
                    step_marker = "checkbox"

                if step_marker == "checkbox":
                    checkbox = page.locator("#EditAppFieldset\\.personal-preferredemployment_Fulltime")
                    await page.wait_for_selector("#EditAppFieldset\\.personal-preferredemployment_Fulltime", timeout=5000)
                    if await checkbox.is_visible() and not await checkbox.is_checked():
                        await checkbox.check()
                    step_marker = "save_and_next"

                if step_marker == "save_and_next":
                    await page.get_by_role("button", name="Save & next").wait_for(timeout=10000)
                    await page.get_by_role("button", name="Save & next").click()
                    await page.get_by_role("button", name="Save & next").click()
                    step_marker = "dropdowns"

                if step_marker == "dropdowns":
                    await page.wait_for_selector("#EditAppFieldset_crbquestions > div.fieldset-fields select")
                    dropdowns = page.locator("#EditAppFieldset_crbquestions > div.fieldset-fields select")
                    count = await dropdowns.count()
                    for i in range(count):
                        options = await dropdowns.nth(i).evaluate("el => Array.from(el.options).map(o => o.value)")
                        if "N" in options:
                            await dropdowns.nth(i).select_option("N")
                    step_marker = "final_save"

                if step_marker == "final_save":
                    await page.get_by_role("button", name="Save").click()
                    await close_toast(page, app_id)
                    await page.locator("#blk_6806_ApplicationForm\\.Complete_Section_PersDetails").click()
                    update_status(app_id, "[Personal] Section completed")
                    break

            except Exception as e:
                update_status(app_id, f"[Personal] Retry {attempt+1}/2: {str(e)}")
                await page.reload()
                await page.wait_for_timeout(2000)
                continue

    except Exception as e:
        update_status(app_id, f"[Personal] Failed: {str(e)}")

# function to fill references 
async def fill_references(page, app_id):
    step_marker = "start"
    update_status(app_id, "[References] Starting")

    for attempt in range(2):
        try:
            if step_marker == "start":
                await page.wait_for_selector("#AppForm_Section_References > div.card-body", timeout=5000)
                await page.locator("#AppForm_Section_References > div.card-body").click()
                step_marker = "edit"

            if step_marker == "edit":
                await page.wait_for_selector("#blk_6806_ApplicationForm\\.Edit_Fieldset_references", timeout=5000)
                await page.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_references").click()
                step_marker = "submit"

            if step_marker == "submit":
                await page.wait_for_selector("#EditAppFieldset\\.Submit", timeout=5000)
                await page.locator("#EditAppFieldset\\.Submit").click()
                await close_toast(page, app_id)
                step_marker = "complete"

            if step_marker == "complete":
                await page.wait_for_selector("#blk_6806_ApplicationForm\\.Complete_Section_References", timeout=5000)
                await page.locator("#blk_6806_ApplicationForm\\.Complete_Section_References").click()
                update_status(app_id, "[References] Completed")
                return

        except Exception as e:
            update_status(app_id, f"[References] Retry {attempt + 1}/2: {str(e)}")
            await page.reload()
            await page.wait_for_timeout(2000)

# function to fill equal opportunities 
async def fill_equal_opportunities(page, app_id):
    step_marker = "start"
    update_status(app_id, "[Equal Ops] Starting")

    for attempt in range(2):
        try:
            # Step 1: Click "Equal Opportunities" section
            if step_marker == "start":
                await page.wait_for_selector("#blk_6806_ApplicationForm\\.Edit_Fieldset_equalops", timeout=5000)
                await page.locator("#blk_6806_ApplicationForm\\.Edit_Fieldset_equalops").click()
                step_marker = "save_next_1"

            # Step 2: Click "Save & next" twice
            if step_marker == "save_next_1":
                await page.get_by_role("button", name="Save & next").click()
                await page.wait_for_timeout(1000)
                await page.get_by_role("button", name="Save & next").click()
                step_marker = "select_source"

            # Step 3: Select "HJUK" from the job source dropdown
            if step_marker == "select_source":
                await page.get_by_label("Please state where you first").select_option("HJUK")
                step_marker = "save_next_2"

            # Step 4: Click "Save & next" again
            if step_marker == "save_next_2":
                await page.get_by_role("button", name="Save & next").click()
                step_marker = "agree_checkbox"

            # Step 5: Agree to declaration (click the checkbox label)
            if step_marker == "agree_checkbox":
                await page.get_by_text("I agree to the above").click()
                step_marker = "final_save"

            # Step 6: Click Save
            if step_marker == "final_save":
                await page.get_by_role("button", name="Save").click()
                step_marker = "close_modal"

            # Step 7: Close any modal or toast (optional)
            if step_marker == "close_modal":
                try:
                    await page.get_by_role("button", name="Close").click(timeout=3000)
                except:
                    pass  # Modal might not show always
                update_status(app_id, "[Equal Ops] Completed")
                return

        except Exception as e:
            update_status(app_id, f"[Equal Ops] Retry {attempt + 1}/2: {str(e)}")
            await page.reload()
            await page.wait_for_timeout(2000)


# the main block of code starts here
def main():
    sg.theme("SystemDefault")
    layout = [
        [sg.Text("Email:"), sg.Input(key="-EMAIL-")],
        [sg.Text("Password:"), sg.Input(key="-PASSWORD-", password_char="*")],
        [sg.Text("Drafts Remaining: "), sg.Text("0", key="-DRAFT-COUNT-")],
        [sg.Multiline(size=(70, 12), key="-STATUS-", disabled=True, autoscroll=True)],
        [sg.Button("Start Automation")]
    ]
    window = sg.Window("Job Application Automation", layout, finalize=True)

    def launch_async_automation(email, password):
        asyncio.run(run_automation(email, password))

    while True:
        event, values = window.read(timeout=1000)
        if event == sg.WIN_CLOSED:
            break

        if event == "Start Automation":
            email = values["-EMAIL-"]
            password = values["-PASSWORD-"]
            if email and password:
                window["-EMAIL-"].update(disabled=True)
                window["-PASSWORD-"].update(disabled=True)
                window["Start Automation"].update(disabled=True)

                threading.Thread(target=launch_async_automation, args=(email, password), daemon=True).start()

        with lock:
            status_lines = "\n".join([f"{k}: {v}" for k, v in status_dict.items()])
        window["-STATUS-"].update(status_lines)
        window["-DRAFT-COUNT-"].update(str(remaining_drafts))

    window.close()

if __name__ == "__main__":
    main()
