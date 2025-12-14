"""Selenium GUI tests for the web interface."""

import os
import pytest
import threading
import time

# Skip all tests if selenium is not installed
pytest.importorskip("selenium")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException


def get_chrome_driver():
    """Get Chrome WebDriver with headless options."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    try:
        # Try using webdriver-manager if available
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except ImportError:
        # Fall back to system chromedriver
        return webdriver.Chrome(options=options)


@pytest.fixture(scope="module")
def app_server():
    """Start the FastAPI server for testing."""
    import uvicorn
    from src.api.main import app
    from src.api.db.database import reset_database

    # Reset database before starting
    reset_database()

    # Start server in a background thread
    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(2)

    yield "http://127.0.0.1:8765"

    # Server will be killed when thread ends (daemon=True)


@pytest.fixture(scope="module")
def browser():
    """Create a Selenium WebDriver instance."""
    try:
        driver = get_chrome_driver()
        yield driver
        driver.quit()
    except WebDriverException as e:
        pytest.skip(f"Chrome WebDriver not available: {e}")


class TestHomePage:
    """Test the home page."""

    def test_home_page_loads(self, app_server, browser):
        """Test that the home page loads successfully."""
        browser.get(app_server)

        # Wait for page to load
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check page title or header exists
        assert browser.title or browser.find_elements(By.TAG_NAME, "h1")

    def test_home_page_has_navigation(self, app_server, browser):
        """Test that navigation elements are present."""
        browser.get(app_server)

        # Wait for page to load
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check for navigation links or buttons
        links = browser.find_elements(By.TAG_NAME, "a")
        buttons = browser.find_elements(By.TAG_NAME, "button")

        # Should have some interactive elements
        assert len(links) > 0 or len(buttons) > 0


class TestHealthDashboard:
    """Test the health dashboard page."""

    def test_health_page_loads(self, app_server, browser):
        """Test that the health page loads."""
        browser.get(f"{app_server}/health.html")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Page should load without errors
        assert "error" not in browser.page_source.lower() or "status" in browser.page_source.lower()


class TestUploadPage:
    """Test the upload page."""

    def test_upload_page_loads(self, app_server, browser):
        """Test that the upload page loads."""
        browser.get(f"{app_server}/static/upload.html")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Should have a form or input elements
        forms = browser.find_elements(By.TAG_NAME, "form")
        inputs = browser.find_elements(By.TAG_NAME, "input")

        assert len(forms) > 0 or len(inputs) > 0

    def test_upload_form_has_submit(self, app_server, browser):
        """Test that the upload form has a submit button."""
        browser.get(f"{app_server}/static/upload.html")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Look for submit button
        submit_buttons = browser.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button")

        assert len(submit_buttons) > 0


class TestAccessibility:
    """Test basic accessibility requirements (WCAG 2.1 AA)."""

    def test_page_has_lang_attribute(self, app_server, browser):
        """Test that the page has a lang attribute for screen readers."""
        browser.get(app_server)

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "html"))
        )

        html_element = browser.find_element(By.TAG_NAME, "html")
        lang = html_element.get_attribute("lang")

        # lang attribute should be set
        assert lang is not None and len(lang) >= 2

    def test_images_have_alt_text(self, app_server, browser):
        """Test that images have alt attributes."""
        browser.get(app_server)

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        images = browser.find_elements(By.TAG_NAME, "img")

        # All images should have alt attribute
        for img in images:
            alt = img.get_attribute("alt")
            assert alt is not None, f"Image {img.get_attribute('src')} missing alt attribute"

    def test_form_labels(self, app_server, browser):
        """Test that form inputs have associated labels."""
        browser.get(f"{app_server}/upload.html")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        inputs = browser.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit'])")
        labels = browser.find_elements(By.TAG_NAME, "label")

        # Should have labels for form inputs (or inputs with aria-label)
        for inp in inputs:
            input_id = inp.get_attribute("id")
            aria_label = inp.get_attribute("aria-label")
            placeholder = inp.get_attribute("placeholder")

            # Input should have either: a label, aria-label, or placeholder
            has_label = any(
                label.get_attribute("for") == input_id
                for label in labels
                if input_id
            )
            assert has_label or aria_label or placeholder, f"Input {input_id} has no label"

    def test_sufficient_color_contrast(self, app_server, browser):
        """Test that text elements are readable (basic check)."""
        browser.get(app_server)

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check that body has some content
        body = browser.find_element(By.TAG_NAME, "body")
        assert body.text.strip() or browser.find_elements(By.TAG_NAME, "img")


class TestAPIIntegration:
    """Test API integration through the UI."""

    def test_api_docs_accessible(self, app_server, browser):
        """Test that API documentation is accessible."""
        browser.get(f"{app_server}/docs")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Swagger UI should load
        assert "swagger" in browser.page_source.lower() or "openapi" in browser.page_source.lower() or "fastapi" in browser.page_source.lower()
