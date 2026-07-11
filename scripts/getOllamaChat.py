from openai import OpenAI

client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama',  # 不需要真实 API 密钥
)

response = client.chat.completions.create(
    model='qwen3:8b',
    messages=[{'role': 'user', 'content': '你是谁?'}],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)