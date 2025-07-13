import PySimpleGUI as sg
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import threading

DRAFT_LIMIT_PER_BATCH = 5  # Number of drafts to open at once

# Shared dictionary to track status
status_dict = {}
lock = threading.Lock()

# Function to update status safely
def update_status(app_id, status):
    with lock:
        status_dict[app_id] = status
        print(status)

# Function to accept cookies
def accept_cookies(page, app_id):
    try:
        update_status(app_id, "Checking for cookie banner")
        page.wait_for_selector("button:has-text('Accept All')", timeout=3000)
        page.get_by_role("button", name="Accept All").click()
        update_status(app_id, "Cookie banner accepted")
        page.screenshot(path=f"cookie_{app_id}.png", full_page=True)
    except PlaywrightTimeoutError:
        update_status(app_id, "No cookie banner found")
    except Exception as e:
        update_status(app_id, f"Cookie error: {str(e)}")

# Function to prompt for new credentials
def prompt_for_credentials(app_id):
    layout = [
        [sg.Text(f"Login failed for {app_id}. Please re-enter credentials:")],
        [sg.Text("Email:"), sg.Input(key="-NEW_EMAIL-")],
        [sg.Text("Password:"), sg.Input(key="-NEW_PASSWORD-", password_char="*")],
        [sg.Button("Retry"), sg.Button("Cancel")]
    ]
    popup = sg.Window(f"Re-enter Credentials for {app_id}", layout, modal=True)
    event, values = popup.read()
    popup.close()
    if event == "Retry" and values["-NEW_EMAIL-"] and values["-NEW_PASSWORD-"]:
        return values["-NEW_EMAIL-"], values["-NEW_PASSWORD-"]
    return None, None

# Function to perform login with improved validation
def login(page, email, password, app_id):
    max_attempts = 3
    attempt = 1
    current_email, current_password = email, password
    while attempt <= max_attempts:
        try:
            update_status(app_id, "Navigating to login page")
            page.goto("https://apps.trac.jobs/")
            accept_cookies(page, app_id)

            update_status(app_id, "Waiting for login form")
            page.wait_for_selector("input[name='FrmCoreLogin-CandidateSignIn_Email']", timeout=8000)

            update_status(app_id, "Entering email")
            page.fill("input[name='FrmCoreLogin-CandidateSignIn_Email']", current_email)
            update_status(app_id, "Entering password")
            page.fill("input[name='FrmCoreLogin-CandidateSignIn_Password']", current_password)
            update_status(app_id, "Submitting login")
            page.get_by_role("button", name="Sign in").click()

            update_status(app_id, "Verifying login")
            page.wait_for_url("https://apps.trac.jobs/dashboard", timeout=10000)
            current_url = page.url
            page_title = page.title()
            update_status(app_id, f"Login successful (URL: {current_url}, Title: {page_title})")

            # Check for error message using a specific selector (adjust based on website HTML)
            error_message = page.query_selector(".error-message, .alert-danger")
            if error_message and "invalid" in error_message.text_content().lower():
                raise Exception(f"Login failed: {error_message.text_content()}")

            return True, current_email, current_password
        except Exception as e:
            update_status(app_id, f"Login error (attempt {attempt}/{max_attempts}): {str(e)}")
            page.screenshot(path=f"login_error_{app_id}_attempt_{attempt}.png", full_page=True)
            if attempt == max_attempts:
                update_status(app_id, "Max login attempts reached")
                return False, current_email, current_password
            update_status(app_id, f"Waiting for new credentials (attempt {attempt}/{max_attempts})")
            new_email, new_password = prompt_for_credentials(app_id)
            if not new_email or not new_password:
                update_status(app_id, "Retry cancelled by user")
                return False, current_email, current_password
            current_email, current_password = new_email, new_password
            attempt += 1

# Function to navigate and get number of drafts applications 
def navigate_and_get_drafts(page, app_id):
    try:
        base_url = "https://apps.trac.jobs/applicationlist?Text=&Status%5B%5D=Draft&Submit=Search&_srt=lastupdateforcandidate&_sd=d&_pg="
        draft_urls = []
        page_number = 1

        # Navigate to Applications and apply filter
        update_status(app_id, "Navigating to applications page")
        page.get_by_role("link", name="Applications", exact=True).click()
        page.wait_for_selector("#AppSearch\\.Status_Draft", timeout=5000)
        page.locator("#AppSearch\\.Status_Draft").click()
        time.sleep(3)

        # Wait for initial drafts to load
        page.wait_for_selector("#ApplicationListResults article a", timeout=5000)
        links = page.locator("#ApplicationListResults article a", has_text="Complete your application")
        total_drafts_on_first_page = links.count()

        # Determine total drafts (estimate from UI count or assume 10 per page)
        # If there's a UI element indicating the total count, use that instead
        total_drafts = total_drafts_on_first_page
        while True:
            try:
                page.wait_for_selector("#ApplicationListResults article", timeout=3000)
                more_links = page.locator("#ApplicationListResults article a", has_text="Complete your application")
                total_drafts = more_links.count()
                break
            except:
                break

        update_status(app_id, f"Initial count shows {total_drafts} drafts on first page")

        # Calculate pages (or loop until no more)
        while True:
            update_status(app_id, f"Scraping page {page_number}")
            paginated_url = f"{base_url}{page_number}"
            page.goto(paginated_url)
            page.wait_for_selector("#ApplicationListResults article a", timeout=5000)
            links = page.locator("#ApplicationListResults article a", has_text="Complete your application")
            count = links.count()

            # sleep for 3 seconds
            time.sleep(3)

            if count == 0:
                update_status(app_id, "No more drafts found")
                break

            for i in range(count):
                href = links.nth(i).get_attribute("href")
                if href:
                    full_url = "https://apps.trac.jobs" + href if href.startswith("/") else href
                    draft_urls.append(full_url)

            update_status(app_id, f"Collected {len(draft_urls)} drafts so far")

            # If fewer than 10 links found, we've reached the last page
            if count < 10:
                break

            page_number += 1

        update_status(app_id, f"Finished. Total drafts collected: {len(draft_urls)}")
        return draft_urls

    except Exception as e:
        update_status(app_id, f"Error navigating or extracting drafts: {str(e)}")
        page.screenshot(path=f"drafts_error_{app_id}.png", full_page=True)
        return []

# opening the different links to begin application 

def apply_to_drafts_in_batches(context, draft_urls, app_id):
    try:
        for i in range(0, len(draft_urls), DRAFT_LIMIT_PER_BATCH):
            batch = draft_urls[i:i + DRAFT_LIMIT_PER_BATCH]
            pages = []
            update_status(app_id, f"Processing batch of {len(batch)} drafts")
            
            # Open drafts concurrently in new tabs
            for url in batch:
                try:
                    page = context.new_page()
                    update_status(app_id, f"Opening draft: {url}")
                    page.goto(url)
                    page.wait_for_timeout(3000)  # Wait 3 seconds
                    update_status(app_id, f"Scrolling to end of {url}")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # Scroll to end
                    update_status(app_id, f"Filling details for {url}")
                    update_status(app_id, f"Applied to: {url}")
                    pages.append(page)
                except Exception as e:
                    update_status(app_id, f"Error applying to {url}: {str(e)}")
            
            # Close all tabs in the batch
            for page in pages:
                update_status(app_id, f"Closing tab for {page.url}")
                page.close()
                time.sleep(0.5)  # Brief delay to ensure clean closure

    except Exception as e:
        update_status(app_id, f"Batch processing error: {str(e)}")


# Main function with UI
def main():
    layout = [
        [sg.Text("Email:"), sg.Input(key="-EMAIL-")],
        [sg.Text("Password:"), sg.Input(key="-PASSWORD-", password_char="*")],
        [sg.Multiline(size=(60, 10), key="-STATUS-", disabled=True)],
        [sg.Button("Start Automation")]
    ]
    window = sg.Window("Job Application Automation", layout, finalize=True)

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

                app_id = "Application"
                update_status(app_id, "Starting automation")
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False)
                    context = browser.new_context()
                    page = context.new_page()

                    try:
                        # Perform login
                        login_result, email, password = login(page, email, password, app_id)
                        if not login_result:
                            update_status(app_id, "Automation aborted due to login failure")
                            break

                        # Get draft URLs
                        draft_urls = navigate_and_get_drafts(page, app_id)
                        if not draft_urls:
                            update_status(app_id, "No drafts found, stopping")
                            break
                        
                        apply_to_drafts_in_batches(context, draft_urls, app_id)


                        update_status(app_id, "Automation completed")
                    except Exception as e:
                        update_status(app_id, f"Automation error: {str(e)}")
                    finally:
                        browser.close()
                        time.sleep(1)  # Ensure browser closes

        # Update status display
        status_text = "\n".join([f"{app_id}: {status}" for app_id, status in status_dict.items()])
        window["-STATUS-"].update(status_text)

    window.close()

if __name__ == "__main__":
    main()


