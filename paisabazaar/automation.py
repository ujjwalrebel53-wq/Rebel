"""Playwright automation for paisabazaar.com (credit score / OTP login)."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Frame, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)

CREDIT_SCORE_URL = "https://www.paisabazaar.com/cibil-credit-report/"
OTP_FRAME_URL_PART = "accounts.paisabazaar.com/otp"


@dataclass
class CreditScoreResult:
    mobile: str
    score: int | None
    message: str
    screenshot_path: Path | None = None


class PaisabazaarAutomation:
    def __init__(self, *, headless: bool = True, artifacts_dir: Path | None = None) -> None:
        self._headless = headless
        self._artifacts_dir = artifacts_dir or Path("artifacts")
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        self._page = await self._context.new_page()

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def _clear_blocking_overlays(self) -> None:
        await self.page.evaluate(
            """() => {
              document
                .querySelectorAll('[data-state="open"][aria-hidden="true"]')
                .forEach((el) => el.remove());
            }"""
        )

    async def open_credit_score_page(self) -> None:
        await self.page.goto(CREDIT_SCORE_URL, wait_until="domcontentloaded", timeout=60_000)
        await self.page.wait_for_timeout(2_000)
        await self._clear_blocking_overlays()

    async def submit_mobile_for_otp(self, mobile: str) -> str:
        """Fill mobile on CIBIL page and trigger OTP. Returns status message."""
        mobile = re.sub(r"\D", "", mobile)
        if len(mobile) != 10 or mobile[0] not in "6789":
            raise ValueError("Valid 10-digit Indian mobile number required (starts with 6–9).")

        await self.open_credit_score_page()

        terms = self.page.locator('label:has-text("By logging in")')
        await terms.click(timeout=10_000)

        await self.page.fill("#mobileNumber", mobile)
        await self._clear_blocking_overlays()

        clicked = await self.page.evaluate(
            """() => {
              const btn = [...document.querySelectorAll("button")].find(
                (b) => b.innerText && b.innerText.includes("Get Free Credit Score")
              );
              if (!btn) return false;
              btn.click();
              return true;
            }"""
        )
        if not clicked:
            raise RuntimeError("Could not find 'Get Free Credit Score' button on page.")

        frame = await self._wait_for_otp_frame(timeout_sec=25)
        if not frame:
            shot = await self._screenshot("otp_frame_missing")
            raise RuntimeError(
                "OTP screen did not load. Check mobile number or try again later."
                + (f" Screenshot: {shot}" if shot else "")
            )

        return (
            f"OTP sent to {mobile[:2]}******{mobile[-2:]}. "
            "Reply with the 4-digit OTP from your SMS."
        )

    async def _wait_for_otp_frame(self, timeout_sec: int = 25) -> Frame | None:
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            for frame in self.page.frames:
                if OTP_FRAME_URL_PART in frame.url:
                    return frame
            await asyncio.sleep(0.5)
        return None

    async def submit_otp_and_fetch_score(self, otp: str, mobile: str) -> CreditScoreResult:
        otp = re.sub(r"\D", "", otp)
        if len(otp) != 4:
            raise ValueError("Paisabazaar OTP is 4 digits.")

        frame = await self._wait_for_otp_frame(timeout_sec=10)
        if not frame:
            await self.submit_mobile_for_otp(mobile)
            frame = await self._wait_for_otp_frame(timeout_sec=15)
        if not frame:
            raise RuntimeError("OTP session expired. Send /cibil to start again.")

        await frame.locator("#ssoOtp, input[name='ssoOtp']").fill(otp)
        verify = frame.locator('button:has-text("Verify"), button:has-text("Login")').first
        await verify.click()

        await self.page.wait_for_timeout(8_000)
        await self._clear_blocking_overlays()

        score = await self._extract_credit_score()
        shot = await self._screenshot("credit_result")
        message = (
            f"Your CIBIL / credit score: *{score}*"
            if score is not None
            else "Logged in. Open dashboard on site if score is not visible in automation."
        )
        return CreditScoreResult(
            mobile=mobile,
            score=score,
            message=message,
            screenshot_path=shot,
        )

    async def _extract_credit_score(self) -> int | None:
        text = await self.page.inner_text("body")
        for frame in self.page.frames:
            try:
                text += "\n" + await frame.locator("body").inner_text()
            except Exception:
                pass

        patterns = [
            r"(?:CIBIL|Credit)\s*Score[^\d]{0,40}(\d{3})",
            r"score[^\d]{0,20}(\d{3})",
            r"\b([6-8]\d{2}|9[0-0]{2})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                if 300 <= value <= 900:
                    return value
        return None

    async def _screenshot(self, name: str) -> Path | None:
        try:
            path = self._artifacts_dir / f"{name}.png"
            await self.page.screenshot(path=str(path), full_page=True)
            return path
        except Exception as exc:
            logger.warning("Screenshot failed: %s", exc)
            return None
