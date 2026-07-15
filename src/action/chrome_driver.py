"""
Chrome Driver — Playwright 直驱版。
独立 Chromium 实例，临时 Profile，不碰用户 Chrome。
"""
import asyncio, json, base64, tempfile, shutil, os
from typing import Optional


PAGE_SUMMARY_JS = """JSON.stringify({
    url: location.href,
    title: document.title || '',
    readyState: document.readyState,
    bodyText: (document.body?.innerText || '').substring(0, 3000),
    interactive: (() => {
        const out = [];
        function walk(root) {
            if (!root?.querySelectorAll) return;
            try { for (const el of root.querySelectorAll('input,textarea,select,button,a,[role]')) {
                const r = el.getBoundingClientRect();
                if (r.width < 1 || r.height < 1) continue;
                try { const cs = getComputedStyle(el);
                    if (cs.visibility === 'hidden' || cs.display === 'none') continue; } catch (_) {}
                let sel = el.id ? '#' + CSS.escape(el.id) : (el.className && typeof el.className === 'string' ?
                    el.tagName.toLowerCase() + '.' + el.className.split(' ').filter(c => c && !c.startsWith('_')).slice(0,2).join('.') :
                    el.tagName.toLowerCase());
                out.push({sel, tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type')||'',
                    placeholder: el.getAttribute('placeholder')||'',
                    aria: el.getAttribute('aria-label')||'',
                    role: el.getAttribute('role')||'',
                    text: (el.textContent||'').trim().substring(0,60)});
                if(out.length>=50) return out;
            }} catch(_) {}
            try { for(const el of root.querySelectorAll('*')){ if(el.shadowRoot) walk(el.shadowRoot); } } catch(_) {}
            return out;
        }
        return walk(document);
    })()
})"""


class ChromeDriver:
    """Playwright 驱动的独立 Chromium 实例。"""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._tmpdir = None

    async def connect(self) -> bool:
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._tmpdir = tempfile.mkdtemp(prefix="chrome_agent_")
            self._browser = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=self._tmpdir, headless=False,
                viewport={"width": 1280, "height": 800})
            self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            print("  [ChromeDriver] Playwright ready")
            return True
        except Exception as e:
            print(f"  [ChromeDriver] error: {e}")
            return False

    async def launch(self) -> bool:
        return await self.connect()

    # === Page ops ===

    async def navigate(self, url: str) -> bool:
        try:
            await self._page.goto(url, wait_until="domcontentloaded")
            return True
        except Exception as e:
            print(f"  [nav] {e}")
            return False

    async def get_page_summary(self) -> dict:
        try:
            raw = await self._page.evaluate(PAGE_SUMMARY_JS)
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}

    async def evaluate(self, js: str) -> dict:
        try:
            return {"result": await self._page.evaluate(js), "error": None}
        except Exception as e:
            return {"error": str(e), "result": None}

    async def get_page_info(self) -> dict:
        try:
            return await self._page.evaluate("() => ({url: location.href, title: document.title || ''})")
        except Exception:
            return {}

    async def get_page_text(self, max_chars: int = 3000) -> str:
        try:
            return await self._page.evaluate(
                f"() => (document.body?.innerText || '').substring(0, {max_chars})")
        except Exception:
            return ""

    async def get_page_elements(self, max_retries: int = 0) -> list[dict]:
        summary = await self.get_page_summary()
        out = []
        for e in summary.get("interactive", []):
            out.append({
                "tag": e.get("tag", ""),
                "label": (e.get("placeholder") or e.get("aria")
                          or e.get("text", "") or e.get("tag", "")),
                "placeholder": e.get("placeholder", ""),
                "aria": e.get("aria", ""), "type": e.get("type", ""),
                "role": e.get("role", ""), "text": e.get("text", ""),
                "bbox": [0, 0, 1, 1], "center": (0, 0),
                "source": "playwright",
            })
        return out

    # === Actions ===

    async def click_at(self, x: float, y: float) -> bool:
        try: await self._page.mouse.click(x, y); return True
        except Exception: return False

    async def type_text(self, text: str) -> bool:
        try: await self._page.keyboard.type(text, delay=30); return True
        except Exception: return False

    async def press_key(self, key: str) -> bool:
        try: await self._page.keyboard.press(key); return True
        except Exception: return False

    async def scroll(self, direction: str = "down", amount: int = 400) -> bool:
        dy = -amount if direction == "up" else amount
        try: await self._page.evaluate(f"window.scrollBy(0, {dy})"); return True
        except Exception: return False

    async def screenshot(self) -> Optional[str]:
        try: data = await self._page.screenshot(type="png"); return base64.b64encode(data).decode()
        except Exception: return None

    async def wait_page_ready(self, timeout_sec: int = 10) -> dict:
        try:
            await self._page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)
            s = await self.get_page_summary()
            return {"ready": len(s.get("interactive", [])) >= 3}
        except Exception:
            return {"ready": False}

    @property
    def is_connected(self) -> bool:
        return self._page is not None

    async def close(self):
        try:
            if self._browser: await self._browser.close()
            if self._playwright: await self._playwright.stop()
            if self._tmpdir and os.path.isdir(self._tmpdir):
                shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass
