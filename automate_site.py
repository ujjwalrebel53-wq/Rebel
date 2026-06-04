"""
Website automation starter (Playwright + Python).

Setup:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  playwright install chromium
  cp .env.example .env   # then edit .env with your site details

Run:
  python automate_site.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

load_dotenv(Path(__file__).resolve().parent / ".env")

SITE_URL = os.getenv("SITE_URL", "").strip()
SITE_USERNAME = os.getenv("SITE_USERNAME", "").strip()
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "").strip()
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")


def login(page: Page) -> None:
    """Customize selectors for your site's login form."""
    # Common patterns — change IDs/names to match your site (Inspect Element in browser)
    page.fill('input[type="email"], input[name="email"], input[name="username"]', SITE_USERNAME)
    page.fill('input[type="password"], input[name="password"]', SITE_PASSWORD)
    page.click('button[type="submit"], input[type="submit"], button:has-text("Log in"), button:has-text("Sign in")')
    page.wait_for_load_state("networkidle")


def run_task(page: Page) -> None:
    """
  Add your automation steps here after login (or on a public page).

  Examples:
    page.click('text=Dashboard')
    page.fill('#search', 'product name')
    page.click('button.search')
    page.screenshot(path='result.png')
  """
    print(f"Current URL: {page.url}")
    print(f"Page title: {page.title()}")


def main() -> int:
    if not SITE_URL:
        print("Set SITE_URL in .env (copy from .env.example)", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-IN",
        )
        page = context.new_page()

        try:
            print(f"Opening {SITE_URL} ...")
            page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60_000)

            if SITE_USERNAME and SITE_PASSWORD:
                print("Logging in ...")
                login(page)

            print("Running task ...")
            run_task(page)

            print("Done.")
            return 0
        except Exception as exc:
            page.screenshot(path="error.png")
            print(f"Failed: {exc}", file=sys.stderr)
            print("Screenshot saved as error.png", file=sys.stderr)
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
