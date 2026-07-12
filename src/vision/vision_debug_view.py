# import requests
# import pyautogui
# from PIL import Image, ImageDraw, ImageFont
# import io
# import os
#
# # 配置 API 地址
# API_URL = "http://localhost:30001/analyze"
#
#
# def get_visual_debug(prompt="<OCR_WITH_REGION>"):
#     # 1. 截取当前屏幕
#     print("📸 正在截取屏幕...")
#     screenshot = pyautogui.screenshot()
#     width, height = screenshot.size
#
#     # 2. 发送给视觉模块
#     img_byte_arr = io.BytesIO()
#     screenshot.save(img_byte_arr, format='PNG')
#     img_byte_arr = img_byte_arr.getvalue()
#
#     print(f"🧠 正在请求红叶进行视觉分析 ({prompt})...")
#     files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
#     params = {'prompt': prompt}
#
#     try:
#         response = requests.post(API_URL, files=files, params=params)
#         data = response.json()
#     except Exception as e:
#         print(f"❌ 连接失败: {e}")
#         return
#
#     # 3. 开始绘图准备
#     draw = ImageDraw.Draw(screenshot)
#
#     # 尝试加载中文字体
#     try:
#         # Windows 微软雅黑路径
#         font = ImageFont.truetype("msyh.ttc", 18)
#     except:
#         font = ImageFont.load_default()
#
#     # 4. 解析 Florence-2 的返回格式
#     # 获取任务对应的结果字典
#     all_data = data.get('data', {})
#     results = all_data.get(prompt, [])
#
#     if not results:
#         print(f"⚠️ 视觉模块未返回任何键名为 {prompt} 的信息。")
#         print(f"收到的原始数据: {data}")
#         return
#
#     # 获取标签和盒子数据
#     labels = results.get('labels', [])
#     # OCR 任务通常返回 quad_boxes，检测任务返回 bboxes
#     boxes = results.get('quad_boxes') or results.get('bboxes')
#
#     if not boxes:
#         print("⚠️ 未找到有效的坐标盒子数据 (quad_boxes/bboxes)。")
#         return
#
#     print(f"🎨 发现目标数量: {len(boxes)}")
#
#     for label, box in zip(labels, boxes):
#         # 初始化归一化坐标
#         nx1, ny1, nx2, ny2 = 0, 0, 0, 0
#
#         if len(box) == 8:
#             # Quad Box 格式: [x1, y1, x2, y2, x3, y3, x4, y4]
#             xs = [box[i] for i in range(0, 8, 2)]
#             ys = [box[i + 1] for i in range(0, 8, 2)]
#             nx1, ny1, nx2, ny2 = min(xs), min(ys), max(xs), max(ys)
#         elif len(box) == 4:
#             # Florence-2 默认返回 [y1, x1, y2, x2]
#             v1, v2, v3, v4 = box
#             ny1, nx1, ny2, nx2 = v1, v2, v3, v4
#         else:
#             continue
#
#         # 坐标转换：1000 归一化 -> 实际像素
#         left = (nx1 / 1000) * width
#         top = (ny1 / 1000) * height
#         right = (nx2 / 1000) * width
#         bottom = (ny2 / 1000) * height
#
#         # 检查坐标是否在屏幕有效范围内，如果完全出界则尝试交换 XY
#         if right < left or bottom < top:
#             left, top, right, bottom = top, left, bottom, right
#
#         # 绘图：亮绿色外框
#         draw.rectangle([left, top, right, bottom], outline="lime", width=3)
#
#         # 绘制文字背景，增强可读性
#         text_content = str(label)
#         draw.text((left + 2, max(0, top - 22)), text_content, fill="lime", font=font)
#
#     # 5. 保存结果并打开图片
#     output_path = "hongye_vision_debug.png"
#     screenshot.save(output_path)
#     print(f"✨ 标注完成！文件已保存至: {os.path.abspath(output_path)}")
#
#     # 自动打开生成的图片
#     try:
#         os.startfile(output_path)
#     except:
#         print(f"请手动打开查看: {output_path}")
#
#
# if __name__ == "__main__":
#     # 执行分析
#     get_visual_debug("<OCR_WITH_REGION>")


import requests
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import io
import os
import ctypes

# 【关键点 1】强制开启 DPI 觉醒，防止 Windows 自动拉伸坐标
try:
    # 适用于 Windows 8.1 及以上
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    # 适用于较老版本 Windows
    ctypes.windll.user32.SetProcessDPIAware()

# 配置 API 地址
API_URL = "http://localhost:30001/analyze"


def get_visual_debug(prompt="<OCR_WITH_REGION>"):
    # 【关键点 2】重新获取屏幕尺寸
    # 在开启 DPI 觉醒后，这里拿到的应该是物理分辨率 (2560x1600)
    print("📸 正在截取屏幕...")
    screenshot = pyautogui.screenshot()
    width, height = screenshot.size
    print(f"检测到物理分辨率: {width} x {height}")

    # 发送给视觉模块
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()

    print(f"🧠 正在请求红叶进行视觉分析 ({prompt})...")
    files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
    params = {'prompt': prompt}

    try:
        response = requests.post(API_URL, files=files, params=params)
        data = response.json()
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    draw = ImageDraw.Draw(screenshot)
    try:
        # 2k/4k 屏幕建议字体调大一点，不然看不清
        font = ImageFont.truetype("msyh.ttc", 25)
    except:
        font = ImageFont.load_default()

    all_data = data.get('data', {})
    results = all_data.get(prompt, [])

    if not results:
        print("⚠️ 视觉模块未返回坐标。")
        return

    labels = results.get('labels', [])
    boxes = results.get('quad_boxes') or results.get('bboxes')

    if not boxes:
        print("⚠️ 未找到有效盒子。")
        return

    # 合并高度重叠的重复框（IoU > 0.5 视为同一目标）
    def merge_overlaps(labels, boxes):
        def to_rect(b):
            if len(b) == 8:
                xs, ys = [b[i] for i in range(0, 8, 2)], [b[i + 1] for i in range(0, 8, 2)]
                return min(xs), min(ys), max(xs), max(ys)
            elif len(b) == 4:
                return b[1], b[0], b[3], b[2]  # [y1,x1,y2,x2] → left,top,right,bottom
            return b[0], b[1], b[2], b[3]

        def iou(a, b):
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            ix, iy = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix >= ix2 or iy >= iy2:
                return 0.0
            inter = (ix2 - ix) * (iy2 - iy)
            area_a = (ax2 - ax1) * (ay2 - ay1)
            area_b = (bx2 - bx1) * (by2 - by1)
            return inter / min(area_a, area_b)

        rects = [to_rect(b) for b in boxes]
        kept = []
        for i, (lbl, rect) in enumerate(zip(labels, rects)):
            merged = False
            for j, (_, kept_rect) in enumerate(kept):
                if iou(rect, kept_rect) > 0.5:
                    merged = True
                    break
            if not merged:
                kept.append((lbl, rect))
        return kept

    merged = merge_overlaps(labels, boxes)
    before = len(boxes)
    boxes = None  # clear original
    print(f"🎨 {before} 个检测 → {len(merged)} 个标注（去重后）")

    for label, rect in merged:
        left, top, right, bottom = rect
        # 纠错：防止顺序颠倒
        real_left, real_right = min(left, right), max(left, right)
        real_top, real_bottom = min(top, bottom), max(top, bottom)

        # 绘图：使用亮绿色，增加线宽以适应高分辨率
        draw.rectangle([real_left, real_top, real_right, real_bottom], outline="lime", width=4)

        # 绘制标签文字，清洗模型特殊 token
        text_str = str(label).replace('</s>', '').replace('<s>', '').strip()
        if not text_str:
            continue
        draw.text((real_left + 5, max(0, real_top - 35)), text_str, fill="lime", font=font)

    # 保存并展示
    output_path = "hongye_2k_debug.png"
    screenshot.save(output_path)
    print(f"✨ 标注完成！路径: {os.path.abspath(output_path)}")
    os.startfile(output_path)


if __name__ == "__main__":
    get_visual_debug("<OCR_WITH_REGION>")