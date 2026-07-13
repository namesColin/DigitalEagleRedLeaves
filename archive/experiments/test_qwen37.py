"""最小测试：Qwen3.7-Plus API"""
import sys, os, io, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from openai import OpenAI
from PIL import Image
from core.config import Config

c = OpenAI(api_key=Config.GLM_API_KEY, base_url=Config.GLM_BASE_URL)

print("测试1 文本...", end=" ", flush=True)
try:
    r = c.chat.completions.create(model=Config.GLM_VISION_MODEL,
        messages=[{"role":"user","content":"回复OK"}], timeout=15)
    print(f"✅ {r.choices[0].message.content}")
except Exception as e: print(f"❌ {e}")

print("测试2 图片...", end=" ", flush=True)
img = Image.new("RGB",(200,100),color="blue")
b=io.BytesIO(); img.save(b,format="PNG"); b64=base64.b64encode(b.getvalue()).decode()
try:
    r = c.chat.completions.create(model=Config.GLM_VISION_MODEL,
        messages=[{"role":"user","content":[{"type":"image_url",
        "image_url":{"url":f"data:image/png;base64,{b64}"}},
        {"type":"text","text":"什么颜色？只回复颜色名"}]}], timeout=30)
    print(f"✅ {r.choices[0].message.content}")
except Exception as e: print(f"❌ {e}")
