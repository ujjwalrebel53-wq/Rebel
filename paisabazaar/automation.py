"""Playwright automation for paisabazaar.com (credit score / OTP login)."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Frame, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)

AUTOMATION_VERSION = "2.2"
CREDIT_SCORE_URL = "https://www.paisabazaar.com/cibil-credit-report/"
ACCOUNTS_HOST = "accounts.paisabazaar.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)


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
        self._otp_ready: bool = False

    async def start(self) -> None:
        if self._browser:
            return
        logger.info("Paisabazaar automation v%s", AUTOMATION_VERSION)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            user_agent=USER_AGENT,
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
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
        self._otp_ready = False

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def _accounts_frames(self) -> list[Frame]:
        return [f for f in self.page.frames if ACCOUNTS_HOST in f.url]

    async def _clear_blocking_overlays(self) -> None:
        await self.page.evaluate(
            """() => {
              document
                .querySelectorAll('[data-state="open"][aria-hidden="true"]')
                .forEach((el) => el.remove());
              document.querySelectorAll('[class*="bg-black"]').forEach((el) => {
                if (el.classList && el.classList.contains("fixed")) el.remove();
              });
            }"""
        )

    async def _accept_terms(self) -> None:
        try:
            await self.page.locator('label:has-text("By logging in")').click(timeout=5_000)
        except Exception:
            pass
        await self.page.evaluate(
            """() => {
              const label = [...document.querySelectorAll("label")].find((l) =>
                l.innerText.includes("By logging in")
              );
              if (label) label.click();
              const cb = document.querySelector('input[type="checkbox"]');
              if (cb) {
                cb.checked = true;
                cb.dispatchEvent(new Event("change", { bubbles: true }));
              }
            }"""
        )

    async def _click_get_score(self) -> None:
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
        if clicked:
            return
        btn = self.page.locator('button:has-text("Get Free Credit Score")').first
        await self._clear_blocking_overlays()
        await btn.click(force=True, timeout=15_000)

    async def _otp_input_visible(self) -> bool:
        for frame in self._accounts_frames():
            try:
                if await frame.locator("#ssoOtp, input[name='ssoOtp']").count() > 0:
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_otp_frame(self, timeout_sec: int = 60) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            if await self._otp_input_visible():
                return True
            await asyncio.sleep(0.5)
        return False

    async def open_credit_score_page(self) -> None:
        await self.page.goto(CREDIT_SCORE_URL, wait_until="domcontentloaded", timeout=90_000)
        await self.page.wait_for_timeout(3_000)
        await self._clear_blocking_overlays()

    async def _submit_mobile_once(self, mobile: str) -> bool:
        await self._accept_terms()
        await self.page.fill("#mobileNumber", mobile)
        await self.page.wait_for_timeout(500)
        await self._click_get_score()
        return await self._wait_for_otp_frame(timeout_sec=60)

    async def submit_mobile_for_otp(self, mobile: str) -> str:
        mobile = re.sub(r"\D", "", mobile)
        if len(mobile) != 10 or mobile[0] not in "6789":
            raise ValueError("Valid 10-digit Indian mobile number required (starts with 6–9).")

        self._otp_ready = False
        await self.open_credit_score_page()

        ok = await self._submit_mobile_once(mobile)
        if not ok:
            logger.info("OTP frame not found, retrying after page reload …")
            await self.open_credit_score_page()
            ok = await self._submit_mobile_once(mobile)

        if not ok:
            shot = await self._screenshot("otp_frame_missing")
            hint = await self._page_error_hint()
            raise RuntimeError(
                "OTP screen load nahi hua. "
                "Mobile Paisabazaar par registered hona chahiye. "
                f"{hint}"
                + (f" Screenshot: {shot}" if shot else "")
            )

        self._otp_ready = True
        return (
            f"OTP sent to {mobile[:2]}******{mobile[-2:]}. "
            "Reply with the 4-digit OTP from your SMS."
        )

    async def _page_error_hint(self) -> str:
        try:
            for text in await self.page.locator(
                '[role="alert"], .text-red-500, [class*="error"]'
            ).all_inner_texts():
                t = text.strip()
                if t:
                    return f"Site message: {t[:120]}"
        except Exception:
            pass
        return ""

    async def _fill_and_verify_otp(self, otp: str) -> None:
        """Fill OTP using real Frame objects only (no FrameLocator / content_frame)."""
        for frame in self._accounts_frames():
            try:
                inp = frame.locator("#ssoOtp, input[name='ssoOtp']")
                if await inp.count() == 0:
                    continue
                await inp.fill(otp, timeout=15_000)
                btn = frame.locator(
                    'button:has-text("Verify"), button:has-text("Login")'
                ).first
                await btn.click(timeout=15_000)
                return
            except Exception as exc:
                logger.warning("OTP fill failed in frame %s: %s", frame.url[:60], exc)

        raise RuntimeError(
            "OTP box iframe mein nahi mila. /cibil se dubara try karo."
        )

    async def submit_otp_and_fetch_score(self, otp: str, mobile: str) -> CreditScoreResult:
        otp = re.sub(r"\D", "", otp)
        if len(otp) != 4:
            raise ValueError("Paisabazaar OTP is 4 digits.")

        if not self._otp_ready and not await self._wait_for_otp_frame(timeout_sec=15):
            await self.submit_mobile_for_otp(mobile)

        if not await self._otp_input_visible():
            if not await self._wait_for_otp_frame(timeout_sec=20):
                raise RuntimeError("OTP session expired. Send /cibil to start again.")

        await self._fill_and_verify_otp(otp)

        await self.page.wait_for_timeout(10_000)
        await self._clear_blocking_overlays()

        score = await self._extract_credit_score()
        shot = await self._screenshot("credit_result")
        message = (
            f"Your CIBIL / credit score: *{score}*"
            if score is not None
            else "Logged in. Dashboard screenshot attached."
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
