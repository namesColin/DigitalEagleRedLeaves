import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image

class VisionModule:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_id = './models/Florence-2-large'
        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, trust_remote_code=True).to(self.device)
        self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        print(f"--- 视觉模块已加载至 {self.device} ---")

    async def analyze(self, image: Image, task_prompt: str):
        """
        task_prompt 示例:
        - '<OCR>': 识别所有文字
        - '<CAPTION>': 描述画面
        - '<OD>': 识别物体（按钮、窗口）
        """
        inputs = self.processor(text=task_prompt, images=image, return_tensors="pt").to(self.device)
        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            do_sample=False,
            num_beams=3
        )
        prediction = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(
            prediction, task=task_prompt, image_size=(image.width, image.height)
        )
        return parsed_answer