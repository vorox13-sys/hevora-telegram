import json
import os
import asyncio
from flask import Flask, request
import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from services.formatter import format_response

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8950788943:AAFIM6325DaYMH9gSxuLOcFOaSk63PNb9vo")
OPENROUTER_API_KEY = "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"
MODEL = "openai/gpt-oss-20b:free"

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

    proxies = {
        "http": "http://proxy.server:3128",
        "https": "http://proxy.server:3128",
    }

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
        proxies=proxies,
        timeout=120,
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})

    conversation_history[chat_id] = history[-20:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        dump_data = json.dump(conversation_history, f, ensure_ascii=False, indent=2)

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

# Application & Flask kurulumu
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("image", image))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

app = Flask(__name__)

import os
from telegram.ext import ApplicationBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN", "BURAYA_TOKEN_YAZ")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handler'ların buraya ekli olmalı (örn: start, message vb.)
    
    print("Bot polling modunda baslatiliyor...")
    application.run_polling()

if __name__ == '__main__':
    main()
