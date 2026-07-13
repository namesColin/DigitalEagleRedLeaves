"""
UI-TARS 桌面 Agent 测试
使用官方 prompt + 官方坐标解析 + pyautogui 执行
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import torch, pyautogui
from PIL import Image
from transformers import AutoProcessor, BitsAndBytesConfig, AutoModelForImageTextToText
from ui_tars.action_parser import parse_action_to_structure_output, parsing_response_to_pyautogui_code

MODEL_PATH = "models/UI-TARS-1.5-7B"

SYSTEM_PROMPT = """You are a GUI agent on Windows desktop. Given a task and screenshot, output the next action.

## Action Space
click(start_box='(x,y)')     - click at coordinates
left_double(start_box='(x,y)') - double click
right_single(start_box='(x,y)') - right click
drag(start_box='(x1,y1)', end_box='(x2,y2)') - drag
hotkey(key='ctrl c')          - press key combination
type(content='text')          - type text
scroll(start_box='(x,y)', direction='down') - scroll
wait()                         - wait 1 second
finished(content='reason')     - task complete

## Output Format
Thought: <reasoning>
Action: <action>"""


def load_model():
    print("加载 UI-TARS (4-bit) ...")
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
    m = AutoModelForImageTextToText.from_pretrained(MODEL_PATH, quantization_config=q, device_map="auto", trust_remote_code=True)
    p = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
    print("✅ 就绪")
    return m, p


def step(model, processor, img, goal, history, original_size=None):
    rw, rh = img.size  # 模型看到的分辨率
    sw, sh = original_size or (rw, rh)  # 屏幕实际分辨率
    msgs = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": f"Task: {goal}\n\nHistory:\n{history}\n\nOutput next action:"},
        ]},
    ]
    prompt = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = processor(text=prompt, images=[img], return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(**inp, max_new_tokens=300, do_sample=False)
    raw = processor.decode(out[0], skip_special_tokens=True).strip()
    # 官方解析：factor=1000 把模型输出归一化，origin 参数告诉解析器模型看的是多大的图
    parsed = parse_action_to_structure_output(raw, factor=1000, origin_resized_height=rh, origin_resized_width=rw)
    # 坐标映射回实际屏幕像素
    code = parsing_response_to_pyautogui_code(parsed, image_height=sh, image_width=sw, scale_factor=1)
    return raw, parsed, code


def run_step(model, processor, goal, history, step_num):
    print(f"\n─ Step {step_num} ─")
    img_raw = pyautogui.screenshot()
    sw, sh = img_raw.size
    img = img_raw.resize((sw // 2, sh // 2))  # 缩小加速推理
    raw, parsed, code = step(model, processor, img, goal, history, original_size=(sw, sh))

    # 显示模型思路
    lines = raw.strip().split("\n")
    for line in lines[-3:]:
        print(f"  {line.strip()[:120]}")

    if not parsed:
        print("  ⚠ 解析失败")
        return f"解析失败", False

    act = parsed[0]
    action_type = act.get("action_type", "")

    # 执行操作
    try:
        if action_type in ("click", "left_single", "left_double", "right_single"):
            # 从 code 字符串提取 pyautogui.click(x, y) 的参数
            import re
            m = re.search(r'pyautogui\.\w+\(([\d.]+),\s*([\d.]+)', code)
            if m:
                x, y = int(float(m.group(1))), int(float(m.group(2)))
                if action_type == "left_double":
                    pyautogui.doubleClick(x, y)
                elif action_type == "right_single":
                    pyautogui.click(x, y, button="right")
                else:
                    pyautogui.click(x, y)
                result = f"{action_type}({x},{y})"
            else:
                result = f"坐标解析失败: {code[:80]}"
        elif action_type == "type":
            content = act["action_inputs"]["content"]
            import pyperclip
            pyperclip.copy(content)
            pyautogui.hotkey("ctrl", "v")
            result = f"输入「{content}」"
        elif action_type == "hotkey":
            keys = act["action_inputs"]["key"].replace(" ", "").split("+")
            pyautogui.hotkey(*keys)
            result = f"热键{' + '.join(keys)}"
        elif action_type == "scroll":
            m = re.search(r'pyautogui\.scroll\(([-\d]+)', code)
            if m:
                pyautogui.scroll(int(m.group(1)))
            result = f"滚动"
        elif action_type == "wait":
            time.sleep(1)
            result = "等待1s"
        elif action_type == "finished":
            result = f"DONE: {act['action_inputs'].get('content', '完成')}"
        elif action_type == "call_user":
            result = f"ASK: {act['action_inputs'].get('content', '?')}"
        else:
            result = f"未知类型: {action_type}"
    except Exception as e:
        result = f"执行错误: {e}"

    print(f"  → {result}")
    return result, action_type == "finished"


def main():
    m, p = load_model()
    goal = input("目标: ").strip() or "打开Chrome进入bilibili主页"
    history = []
    for st in range(1, 25):
        result, done = run_step(m, p, goal, "\n".join(history[-5:]) if history else "（尚无）", st)
        history.append(f"S{st}: {result}")
        if done:
            print(f"\n✅ {result}")
            return
        if result.startswith("ASK"):
            ans = input(f"\n  🤔 {result}\n  → ").strip()
            history.append(f"用户: {ans}")
            goal = f"{goal}（补充：{ans}）"
        time.sleep(2)
    print("\n⚠ 上限")


if __name__ == "__main__":
    main()
