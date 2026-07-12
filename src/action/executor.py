"""执行层：pyautogui 键鼠操作 + 截图验证"""
import time
import pyautogui
import io
from PIL import Image

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def screenshot() -> Image.Image:
    return pyautogui.screenshot()


def screenshot_to_bytes() -> bytes:
    buf = io.BytesIO()
    pyautogui.screenshot().save(buf, format="PNG")
    return buf.getvalue()


def click_center(bbox: list):
    x = int((bbox[0] + bbox[2]) / 2)
    y = int((bbox[1] + bbox[3]) / 2)
    pyautogui.click(x, y)


def click_at(x: int, y: int):
    pyautogui.click(x, y)


def type_text(text: str, interval: float = 0.05):
    pyautogui.write(text, interval=interval)


def press(key: str):
    pyautogui.press(key)


def hotkey(*keys: str):
    pyautogui.hotkey(*keys)


def scroll(amount: int):
    pyautogui.scroll(amount)


def wait(seconds: float):
    time.sleep(seconds)


def screen_size() -> tuple[int, int]:
    return pyautogui.size()
