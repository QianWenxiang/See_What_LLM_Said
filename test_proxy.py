import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
BASE_URL = "http://localhost:7654"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

def test_models_endpoint():
    print("\n[Test 1] 正在测试 GET /v1/models (探活接口)")
    url = f"{BASE_URL}/v1/models"
    try:
        response = requests.get(url, timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        if response.status_code == 200:
            print("✅ 探活接口测试通过！")
        else:
            print("❌ 探活接口测试失败！")
    except Exception as e:
        print(f"❌ 请求发生异常: {e}")

def test_chat_completions():
    print("\n[Test 2] 正在测试 POST /v1/chat/completions (大模型对话)")
    url = f"{BASE_URL}/v1/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好，你是什么模型。"}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer TEST_KEY_123" # 插件随便传的 key，服务端会自动覆盖为真实的
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        print(f"Status Code: {response.status_code}")
        try:
            print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        except Exception:
            print(f"Raw Response: {response.text}")
            
        if response.ok:
            print("✅ 聊天接口测试通过,LLM 成功返回了数据。")
        else:
            print("❌ 聊天接口抛出了错误！请检查你的真实 .env 配置是否正确。")
    except Exception as e:
        print(f"❌ 请求发生异常: {e}")

if __name__ == "__main__":
    print(f"正在测试目标地址: {BASE_URL}")
    test_models_endpoint()
    test_chat_completions()
    print("\n测试完成。")
