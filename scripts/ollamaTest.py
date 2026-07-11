import requests
import json


def start_model_via_api(model_name):
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": "",
        "stream": False
    }

    # 关键：显式设置 proxies 为 None，彻底绕过系统代理，解决 502 报错
    proxies = {
        "http": None,
        "https": None,
    }

    try:
        print(f"正在启动模型 {model_name}，请稍候（显存加载中）...")
        response = requests.post(url, json=payload, proxies=proxies, timeout=60)

        if response.status_code == 200:
            print("✅ 模型已成功加载到服务中！")
            print("响应结果:", response.json())
        else:
            print(f"❌ 启动失败，状态码: {response.status_code}")
            print("错误详情:", response.text)

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 Ollama 服务，请确保已运行 'ollama serve'")
    except Exception as e:
        print(f"❌ 发生异常: {e}")


def refresh_models(self):
    import requests
    import os

    self.model_combo.clear()

    # 定义 API 地址
    url = "http://127.0.0.1:11434/api/tags"

    # 彻底禁用代理，防止请求被转发到 11434 端口自身导致 502
    proxies = {"http": None, "https": None}

    try:
        # 发送 GET 请求
        response = requests.get(url, proxies=proxies, timeout=3)

        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])

            if not models:
                print("Ollama 中尚未下载任何模型。")
                self.model_combo.addItem("未发现本地模型")
                return

            # 解析模型名称
            for model_info in models:
                name = model_info.get('name')
                if name:
                    # 避免重复添加
                    if name not in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
                        self.model_combo.addItem(name)

            print(f"已通过 API 刷新 {len(models)} 个模型")
        else:
            print(f"获取模型列表失败，状态码: {response.status_code}")
            self.model_combo.addItem("无法获取列表 (API 错误)")

    except Exception as e:
        print(f"刷新模型列表时发生异常: {e}")
        self.model_combo.addItem("Ollama 未启动或连接超时")

if __name__ == "__main__":
    # 获取 Ollama 模型列表
    start_model_via_api("qwen3:8b")
    # refresh_models(None)  # 这里传 None 仅为测试，实际使用时应传入正确的 self 对象