import os
import requests

def analyze_image(image_path, user_prompt="Bu görselde ne görüyorsun? Açıkla."):
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    # Vision destekli güçlü bir model seçiyoruz
    MODEL = "qwen/qwen-2.5-vl-72b-instruct"

    import base64
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()
    return data["choices"][0]["message"]["content"]
