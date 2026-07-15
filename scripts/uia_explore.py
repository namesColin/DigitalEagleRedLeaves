"""
UIA 探测脚本 — 摸底 Windows UI Automation 能覆盖多少控件
输出: outputs/uia_scan.json
"""
import json, os, time
import uiautomation as auto


def describe_control(c):
    """提取控件关键信息"""
    info = {
        "name": "",
        "type": "",
        "rect": None,
        "enabled": False,
        "visible": False,
        "focused": False,
    }
    try:
        info["name"] = c.Name or ""
    except Exception:
        pass
    try:
        info["type"] = c.ControlTypeName or ""
    except Exception:
        pass
    try:
        r = c.BoundingRectangle
        if r:
            info["rect"] = [r.left, r.top, r.right - r.left, r.bottom - r.top]
    except Exception:
        pass
    try:
        info["enabled"] = c.IsEnabled
    except Exception:
        pass
    try:
        info["visible"] = not c.IsOffscreen
    except Exception:
        pass
    try:
        info["focused"] = c.HasKeyboardFocus
    except Exception:
        pass
    return info


def walk_tree(control, depth=0, max_depth=5):
    """递归遍历控件树"""
    if depth > max_depth:
        return []
    results = []
    info = describe_control(control)
    if info["name"] or info["rect"]:
        info["depth"] = depth
        results.append(info)
    try:
        for child in control.GetChildren():
            results.extend(walk_tree(child, depth + 1, max_depth))
    except Exception:
        pass
    return results


def scan_desktop():
    """扫描桌面所有窗口"""
    all_windows = []
    print("Scanning desktop windows...\n")

    root = auto.GetRootControl()
    try:
        top_windows = root.GetChildren()
    except Exception:
        top_windows = []

    for i, win in enumerate(top_windows):
        w_info = describe_control(win)
        if not w_info["name"] or not w_info["rect"]:
            continue
        w, h = w_info["rect"][2], w_info["rect"][3]
        if w < 50 or h < 50:
            continue

        print(f"[{i}] {w_info['name'][:60]:60s} | {w_info['type']:20s} | {w}x{h}")
        children = walk_tree(win, 0, max_depth=6)
        w_info["children"] = children
        all_windows.append(w_info)
        if children:
            named = [c for c in children if c["name"] and c["depth"] <= 2]
            for nc in named[:8]:
                label = nc["name"][:50]
                t = nc["type"] or "?"
                r = nc["rect"]
                pos = f"({r[0]},{r[1]})" if r else ""
                print(f"    |-- [{t}] \"{label}\" {pos}")
            if len(named) > 8:
                print(f"    ... +{len(named)-8} more")

    print(f"\nTotal: {len(all_windows)} windows")
    os.makedirs("outputs", exist_ok=True)
    out_path = "outputs/uia_scan.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "windows": all_windows}, f, ensure_ascii=False, indent=2)
    print(f"Written to {out_path}")
    return all_windows


if __name__ == "__main__":
    scan_desktop()
