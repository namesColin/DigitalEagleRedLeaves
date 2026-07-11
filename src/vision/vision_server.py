import io
from fastapi import FastAPI, UploadFile, File
from PIL import Image
from .vision_model import VisionModule
import uvicorn

app = FastAPI()
# 初始化视觉模型
vision = VisionModule()

@app.post("/analyze")
async def analyze_screen(file: UploadFile = File(...), prompt: str = "<OCR>"):
    """
    接收图片并返回识别结果
    prompt 选项:
    - '<OCR>': 提取文字
    - '<OCR_WITH_REGION>': 提取文字及坐标
    - '<DETAILED_CAPTION>': 详细描述画面内容
    - '<OD>': 目标检测（识别按钮、图标等）
    """
    # 1. 读取上传的图片内容
    request_object_content = await file.read()
    image = Image.open(io.BytesIO(request_object_content)).convert("RGB")

    # 2. 调用模型推理
    result = await vision.analyze(image, prompt)

    # 3. 返回 JSON 结果
    return {"status": "success", "data": result}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=30001)