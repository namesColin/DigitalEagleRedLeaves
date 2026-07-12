"""
VisionModuleV2 —— OmniParser 架构的视觉模块

架构: YOLOv8 (OmniParser UI 权重) 检测 + Florence-2-large (已有) 描述
相比 V1: 检测语义化 / NMS 内置 / 无重叠框 / 检测描述分离
"""
import torch
import numpy as np
from PIL import Image
from ultralytics import YOLO
from transformers import AutoProcessor, AutoModelForCausalLM


class VisionModuleV2:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32

        import os
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _omni = os.path.join(_root, "models", "OmniParser-v2.0")
        _florence = os.path.join(_root, "models", "Florence-2-large")
        _omni_caption = os.path.join(_omni, "icon_caption_florence")

        print("[V2] 加载 YOLO 检测器 ...")
        self.yolo = YOLO(os.path.join(_omni, "icon_detect", "model.pt"))

        print("[V2] 加载 OmniParser UI 微调 caption 模型 ...")
        # processor 通用，用已有的 large 即可（同架构）；model 用 OmniParser 微调权重
        self.processor = AutoProcessor.from_pretrained(_florence, trust_remote_code=True)
        self.caption_model = AutoModelForCausalLM.from_pretrained(
            _omni_caption, trust_remote_code=True, attn_implementation="eager", dtype=self.dtype
        ).to(self.device)

        print(f"--- 视觉模块 V2 就绪 ({self.device}) ---")

    async def analyze(self, image: Image.Image, task_prompt: str = "<OD>"):
        w, h = image.size

        if "CAPTION" in task_prompt:
            return await self._describe_full(image)

        # YOLO 检测 (提高阈值减少低质量框，100+ → ~20)
        results = self.yolo.predict(image, conf=0.15, iou=0.5, verbose=False)[0]
        if results.boxes is None:
            return {"boxes": [], "labels": [], "format": "xyxy_pixel"}

        boxes = results.boxes.xyxy.cpu().tolist()

        # Florence-2 批量描述
        labels = await self._caption_boxes(image, boxes)

        return {"boxes": boxes, "labels": labels, "format": "xyxy_pixel",
                "model": "OmniParser-YOLO + Florence-2-large"}

    async def _caption_boxes(self, image, boxes, batch_size=16):
        image_np = np.asarray(image)
        captions = []

        for i in range(0, len(boxes), batch_size):
            batch = boxes[i:i + batch_size]
            crops = []
            for (x1, y1, x2, y2) in batch:
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(image_np.shape[1], int(x2)), min(image_np.shape[0], int(y2))
                crops.append(Image.fromarray(image_np[y1:y2, x1:x2, :]))

            inputs = self.processor(
                images=crops, text=["<CAPTION>"] * len(crops), return_tensors="pt"
            ).to(self.device)
            if self.device == "cuda":
                inputs["pixel_values"] = inputs["pixel_values"].to(self.dtype)

            with torch.inference_mode():
                g = self.caption_model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=20, num_beams=1, do_sample=False,
                    use_cache=False, early_stopping=False,
                )
            captions += [t.strip() for t in
                         self.processor.batch_decode(g, skip_special_tokens=True)]

        return captions

    async def _describe_full(self, image):
        inputs = self.processor(
            images=image, text="<DETAILED_CAPTION>", return_tensors="pt"
        ).to(self.device)
        if self.device == "cuda":
            inputs["pixel_values"] = inputs["pixel_values"].to(self.dtype)

        with torch.inference_mode():
            g = self.caption_model.generate(
                input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                max_new_tokens=100, num_beams=1, do_sample=False,
                use_cache=False, early_stopping=False,
            )
        return {"caption": self.processor.batch_decode(g, skip_special_tokens=True)[0],
                "format": "text"}
