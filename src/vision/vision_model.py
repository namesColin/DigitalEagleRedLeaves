import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image


# vision_model.py

class VisionModule:
    def __init__(self):
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_id = './models/Florence-2-large'

        # 记录模型使用的精度
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            attn_implementation="eager",
            torch_dtype=self.dtype  # 统一使用 self.dtype
        ).to(self.device)

        self.processor = AutoProcessor.from_pretrained(
            self.model_id,
            trust_remote_code=True
        )
        print(f"--- 视觉模块已加载至 {self.device} ({self.dtype}) ---")

    async def analyze(self, image, task_prompt: str):
        import torch
        # 1. 预处理
        inputs = self.processor(text=task_prompt, images=image, return_tensors="pt").to(self.device)

        # 2. 精度转换
        if self.device == "cuda":
            inputs = {k: v.to(self.dtype) if k == "pixel_values" else v for k, v in inputs.items()}

        # 3. 推理核心
        with torch.no_grad():
            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
                # --- 关键修复参数 ---
                use_cache=False,  # 强制禁用缓存，解决 past_key_values 为 None 的问题
                early_stopping=False
            )

        # 4. 后处理
        prediction = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(
            prediction, task=task_prompt, image_size=(image.width, image.height)
        )
        return parsed_answer