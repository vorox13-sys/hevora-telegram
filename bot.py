import json
import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from services.formatter import format_response

# --- FLASK MINI SUNUCU (Render'ı uyutmama trick'i) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Hevora Nano Bot aktif ve uyanık! 🚀"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)
# ----------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("MODEL", "qwen/qwen-2.5-72b-instruct")

SYSTEM_PROMPT = """
Sen Hevora Nano'sun.
Her zaman Türkçe cevap ver.
Kısa, doğal ve doğru konuş.
"""

MEMORY_FILE = "memory.json"

if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        conversation_history = json.load(f)
else:
    conversation_history = {}

def ask_ai(chat_id, user_message):
    chat_id = str(chat_id)
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    history = conversation_history[chat_id]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 3000,
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})

    conversation_history[chat_id] = history[-20:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=2)

    return answer

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Merhaba!\n\n"
        "Ben Hevora Nano.\n"
        "Bana istediğini sorabilirsin.\n\n"
        "🖼 Görsel oluşturmak için:\n"
        "/image kırmızı spor araba"
    )

async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Kullanım:\n/image astronot kedi")
        return

    url = (
        "https://image.pollinations.ai/prompt/"
        + requests.utils.quote(prompt)
        + "?model=flux&width=1024&height=1024&nologo=true"
    )
    await update.message.reply_photo(photo=url)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    try:
        answer = ask_ai(update.effective_chat.id, text)
        parts, mode = format_response(answer)
        for part in parts:
            await update.message.reply_text(
                part, parse_mode=mode, disable_web_page_preview=True
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Hata:\n{e}")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN çevre değişkeni bulunamadı!")

    # Flask'ı arka planda (ayrı bir thread'de) çalıştırıyoruz
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Telegram botunu başlatıyoruz
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot polling modunda ve web sunucu ile baslatiliyor...")
    app.run_polling()

if __name__ == '__main__':
    main()
