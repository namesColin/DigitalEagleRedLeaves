import requests
import pyautogui
from PIL import Image
import io


def capture_and_analyze(prompt="<OCR_WITH_REGION>"):
    # 1. 截取全屏
    screenshot = pyautogui.screenshot()

    # 2. 转换为字节流
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()

    # 3. 发送给视觉 API
    files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
    params = {'prompt': prompt}

    response = requests.post("http://localhost:30001/analyze", files=files, params={'prompt': prompt})

    # 调试：打印服务器状态码和原始内容
    if response.status_code != 200:
        print(f"服务器报错了！状态码: {response.status_code}")
        print(f"错误内容: {response.text}")
        return None

    return response.json()

# 测试：看看能不能认出屏幕上的字
print(capture_and_analyze("<OCR>"))