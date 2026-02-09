"""Application submission engine using Selenium for browser automation."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from job_agent.config import AgentConfig
from job_agent.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobBoard,
    UserProfile,
)

logger = logging.getLogger(__name__)


class ApplicatorEngine:
    """Submits job applications using browser automation."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._driver = None

    def _get_driver(self):
        """Lazy-load Selenium WebDriver."""
        if self._driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            if self.config.browser.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])

            if self.config.browser.user_agent:
                options.add_argument(
                    f"--user-agent={self.config.browser.user_agent}"
                )

            if self.config.browser.proxy:
                options.add_argument(f"--proxy-server={self.config.browser.proxy}")

            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=options)
            self._driver.implicitly_wait(self.config.browser.timeout)

        return self._driver

    def apply(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> ApplicationRecord:
        """Submit an application based on the job board type."""
        job = application.job
        logger.info(f"Applying to {job.title} at {job.company} via {job.board.value}")

        application.update_status(ApplicationStatus.APPLYING)

        try:
            handler = {
                JobBoard.LINKEDIN: self._apply_linkedin,
                JobBoard.INDEED: self._apply_indeed,
                JobBoard.GLASSDOOR: self._apply_glassdoor,
                JobBoard.ZIPRECRUITER: self._apply_ziprecruiter,
                JobBoard.HEIDRICK: self._apply_external_only,
                JobBoard.KORNFERRY: self._apply_external_only,
                JobBoard.SPENCERSTUART: self._apply_external_only,
                JobBoard.RUSSELLREYNOLDS: self._apply_external_only,
            }.get(job.board)

            if handler is None:
                raise ValueError(f"Unsupported job board: {job.board}")

            success = handler(application, profile)

            if success:
                application.update_status(
                    ApplicationStatus.SUBMITTED, "Application submitted successfully"
                )
                logger.info(f"Successfully applied to {job.title} at {job.company}")
            else:
                application.update_status(
                    ApplicationStatus.FAILED, "Application submission failed"
                )
                logger.warning(f"Failed to apply to {job.title} at {job.company}")

        except Exception as e:
            application.update_status(
                ApplicationStatus.FAILED, f"Error: {str(e)}"
            )
            logger.error(f"Application error for {job.title}: {e}")

        return application

    def _apply_external_only(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle executive recruiting firm listings - log for manual follow-up."""
        job = application.job
        application.notes = (
            f"Executive recruiting listing - apply directly at: {job.url}\n"
            f"Board: {job.board.value}\n"
            f"These positions typically require direct contact with the recruiting firm."
        )
        logger.info(
            f"External-only listing from {job.board.value}: {job.title} at {job.company}. "
            f"URL saved for manual follow-up: {job.url}"
        )
        return True

    def _apply_linkedin(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle LinkedIn Easy Apply."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = self._get_driver()
        job = application.job

        try:
            # Login if needed
            self._linkedin_login(profile)

            driver.get(job.url)
            time.sleep(2)

            # Look for Easy Apply button
            try:
                easy_apply_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, ".jobs-apply-button, button[data-control-name='jobdetails_topcard_inapply']")
                    )
                )
                easy_apply_btn.click()
                time.sleep(1)
            except Exception:
                logger.info("No Easy Apply button found, opening external link")
                application.notes = "Redirected to external application page"
                return self._handle_external_apply(driver, application, profile)

            # Handle Easy Apply modal steps
            return self._complete_linkedin_easy_apply(driver, application, profile)

        except Exception as e:
            logger.error(f"LinkedIn apply failed: {e}")
            return False

    def _linkedin_login(self, profile: UserProfile) -> None:
        """Login to LinkedIn."""
        from selenium.webdriver.common.by import By

        driver = self._get_driver()
        email = os.getenv("LINKEDIN_EMAIL", "")
        password = os.getenv("LINKEDIN_PASSWORD", "")

        if not email or not password:
            raise ValueError("LinkedIn credentials not configured")

        driver.get("https://www.linkedin.com/login")
        time.sleep(2)

        email_input = driver.find_element(By.ID, "username")
        password_input = driver.find_element(By.ID, "password")

        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)

        driver.find_element(
            By.CSS_SELECTOR, "button[type='submit']"
        ).click()
        time.sleep(3)

    def _complete_linkedin_easy_apply(
        self, driver, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Navigate through LinkedIn Easy Apply multi-step form."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_steps = 10
        for step in range(max_steps):
            time.sleep(1)

            # Fill in any visible form fields
            self._fill_form_fields(driver, profile, application)

            # Upload resume if file input is present
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if file_inputs and application.tailored_resume_path:
                for fi in file_inputs:
                    try:
                        fi.send_keys(application.tailored_resume_path)
                        time.sleep(1)
                    except Exception:
                        pass

            # Check for submit button
            try:
                submit_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[aria-label*='Submit'], button[aria-label*='submit']"
                )
                submit_btn.click()
                time.sleep(2)
                logger.info("Clicked submit button")
                return True
            except Exception:
                pass

            # Click next/continue button
            try:
                next_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[aria-label*='Continue'], button[aria-label*='Next'], "
                    "button[aria-label*='Review']"
                )
                next_btn.click()
                time.sleep(1)
            except Exception:
                logger.warning(f"No next/submit button found at step {step + 1}")
                break

        return False

    def _apply_indeed(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle Indeed Easy Apply."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = self._get_driver()
        job = application.job

        try:
            driver.get(job.url)
            time.sleep(2)

            # Look for Apply button
            try:
                apply_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "#indeedApplyButton, .indeed-apply-button, button[id*='apply']")
                    )
                )
                apply_btn.click()
                time.sleep(2)
            except Exception:
                logger.info("No Indeed Apply button found")
                return False

            # Fill form fields
            self._fill_form_fields(driver, profile, application)

            # Upload resume
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if file_inputs and application.tailored_resume_path:
                file_inputs[0].send_keys(application.tailored_resume_path)
                time.sleep(2)

            # Navigate through steps and submit
            for _ in range(5):
                try:
                    continue_btn = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[id*='continue'], button.ia-continueButton, "
                        "button[type='submit']"
                    )
                    continue_btn.click()
                    time.sleep(2)
                except Exception:
                    break

            return True

        except Exception as e:
            logger.error(f"Indeed apply failed: {e}")
            return False

    def _apply_glassdoor(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle Glassdoor Easy Apply."""
        from selenium.webdriver.common.by import By

        driver = self._get_driver()
        job = application.job

        try:
            driver.get(job.url)
            time.sleep(2)

            try:
                apply_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button.easyApply, [data-test='applyButton'], .apply-button"
                )
                apply_btn.click()
                time.sleep(2)
            except Exception:
                logger.info("No Glassdoor Easy Apply button found")
                application.notes = "External application required"
                return False

            self._fill_form_fields(driver, profile, application)

            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if file_inputs and application.tailored_resume_path:
                file_inputs[0].send_keys(application.tailored_resume_path)
                time.sleep(2)

            try:
                submit_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit'], .submit-application"
                )
                submit_btn.click()
                time.sleep(2)
                return True
            except Exception:
                return False

        except Exception as e:
            logger.error(f"Glassdoor apply failed: {e}")
            return False

    def _apply_ziprecruiter(
        self, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle ZipRecruiter one-click apply."""
        from selenium.webdriver.common.by import By

        driver = self._get_driver()
        job = application.job

        try:
            driver.get(job.url)
            time.sleep(2)

            try:
                apply_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    ".quick-apply, .one-click-apply, "
                    "button[data-testid='apply-button']"
                )
                apply_btn.click()
                time.sleep(2)
            except Exception:
                logger.info("No ZipRecruiter quick apply button found")
                return False

            self._fill_form_fields(driver, profile, application)

            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if file_inputs and application.tailored_resume_path:
                file_inputs[0].send_keys(application.tailored_resume_path)
                time.sleep(2)

            try:
                submit_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[type='submit'], .submit-btn, "
                    "[data-testid='submit-application']"
                )
                submit_btn.click()
                time.sleep(2)
                return True
            except Exception:
                return False

        except Exception as e:
            logger.error(f"ZipRecruiter apply failed: {e}")
            return False

    def _fill_form_fields(
        self, driver, profile: UserProfile, application: ApplicationRecord
    ) -> None:
        """Auto-fill common form fields with profile data."""
        from selenium.webdriver.common.by import By

        field_map = {
            "first_name": profile.first_name,
            "firstName": profile.first_name,
            "last_name": profile.last_name,
            "lastName": profile.last_name,
            "email": profile.email,
            "phone": profile.phone,
            "phoneNumber": profile.phone,
            "city": profile.location,
            "linkedin": profile.linkedin_url,
            "website": profile.portfolio_url,
            "github": profile.github_url,
        }

        for field_name, value in field_map.items():
            if not value:
                continue
            try:
                inputs = driver.find_elements(
                    By.CSS_SELECTOR,
                    f"input[name*='{field_name}' i], "
                    f"input[id*='{field_name}' i], "
                    f"input[aria-label*='{field_name}' i]"
                )
                for inp in inputs:
                    if inp.is_displayed() and not inp.get_attribute("value"):
                        inp.clear()
                        inp.send_keys(value)
            except Exception:
                pass

        # Fill cover letter text areas
        if application.cover_letter_path:
            try:
                cover_text = Path(application.cover_letter_path).read_text()
                textareas = driver.find_elements(
                    By.CSS_SELECTOR,
                    "textarea[name*='cover' i], textarea[id*='cover' i], "
                    "textarea[aria-label*='cover' i], "
                    "textarea[name*='message' i]"
                )
                for ta in textareas:
                    if ta.is_displayed() and not ta.get_attribute("value"):
                        ta.clear()
                        ta.send_keys(cover_text)
            except Exception:
                pass

    def _handle_external_apply(
        self, driver, application: ApplicationRecord, profile: UserProfile
    ) -> bool:
        """Handle external application links."""
        from selenium.webdriver.common.by import By

        try:
            external_link = driver.find_element(
                By.CSS_SELECTOR,
                "a[data-control-name='jobdetails_topcard_inapply'], "
                "a.apply-button, a[href*='apply']"
            )
            url = external_link.get_attribute("href")
            if url:
                application.job.application_url = url
                application.notes = f"External application URL: {url}"
                driver.get(url)
                time.sleep(3)
                self._fill_form_fields(driver, profile, application)
                return True
        except Exception:
            pass
        return False

    def close(self) -> None:
        """Clean up browser resources."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
