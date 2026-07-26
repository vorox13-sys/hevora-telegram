import os
import requests
import base64

VISION_MODELS = [
    "qwen/qwen-2.5-vl-72b-instruct",
    "google/gemini-2.5-flash:free"
]

def analyze_image(image_path, user_prompt="Bu görselde ne görüyorsun? Açıkla."):
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

    last_error = None
    for model in VISION_MODELS:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
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
                timeout=45,
            )

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                last_error = response.text
        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"Görsel analizi için hiçbir model yanıt vermedi. Hata: {last_error}")
