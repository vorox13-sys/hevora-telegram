import os
import pypdf
import requests

def extract_text_ring_pdf(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def analyze_pdf(pdf_path, user_prompt="Bu PDF belgesini detaylıca özetle."):
    pdf_text = extract_text_ring_pdf(pdf_path)
    if not pdf_text.strip():
        return "PDF dosyasından metin çıkarılamadı (taranmış resim olabilir)."

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    MODEL = os.getenv("MODEL", "qwen/qwen-2.5-72b-instruct")

    prompt = f"{user_prompt}\n\nPDF İçeriği:\n{pdf_text[:12000]}" # Token sınırını aşmamak için kırpma

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()
    return data["choices"][0]["message"]["content"]
