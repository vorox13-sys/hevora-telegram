import json
import os
import threading
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from services.formatter import format_response
from voice import text_to_speech
from image import analyze_image
from pdf import analyze_pdf

# --- FLASK MINI SUNUCU ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Hevora Nano Bot aktif ve uyanık! 🚀"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)
# -------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("MODEL", "qwen/qwen-2.5-72b-instruct")

SYSTEM_PROMPT = """
Sen Hevora Nano'sun. Hevora Labs tarafından geliştirilmiş gelişmiş bir yapay zeka asistanısın.
Her zaman Türkçe cevap ver.
Kısa, doğal, profesyonel ve doğru konuş.
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
        "Ben **Hevora Nano**, **Hevora Labs** tarafından geliştirildim.\n"
        "Bana metin, görsel veya PDF dosyası gönderebilirsin.\n\n"
        "🖼 Görsel üretmek için:\n"
        "/image kırmızı spor araba",
        parse_mode="Markdown"
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
        
        keyboard = [[InlineKeyboardButton("🔊 Sesli Dinle", callback_data="tts_play")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for i, part in enumerate(parts):
            markup = reply_markup if i == len(parts) - 1 else None
            await update.message.reply_text(
                part, parse_mode=mode, disable_web_page_preview=True, reply_markup=markup
            )
    except Exception as e:
        print(f"Arka plan hatası (Gizlenen Log): {e}")
        await update.message.reply_text("⚠️ Şu anda yapay zeka servislerinde geçici bir yoğunluk var. Lütfen birkaç saniye sonra tekrar dene.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = "temp_image.jpg"
    await file.download_to_drive(file_path)

    caption = update.message.caption or "Bu görseli açıkla."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        result = analyze_image(file_path, caption)
        parts, mode = format_response(result)
        for part in parts:
            await update.message.reply_text(part, parse_mode=mode)
    except Exception as e:
        print(f"Görsel analiz hatası: {e}")
        await update.message.reply_text("⚠️ Görsel analiz edilirken bir hata oluştu.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Şimdilik sadece PDF dosyalarını analiz edebiliyorum.")
        return

    file = await context.bot.get_file(document.file_id)
    file_path = "temp_doc.pdf"
    await file.download_to_drive(file_path)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        result = analyze_pdf(file_path)
        parts, mode = format_response(result)
        for part in parts:
            await update.message.reply_text(part, parse_mode=mode)
    except Exception as e:
        print(f"PDF analiz hatası: {e}")
        await update.message.reply_text("⚠️ PDF okunurken bir hata oluştu.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tts_play":
        target_text = query.message.text or "Sesli yanıt."
        audio_file = await text_to_speech(target_text)
        
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, "rb") as voice:
                await context.bot.send_voice(chat_id=query.message.chat_id, voice=voice)
            os.remove(audio_file)
        else:
            await query.edit_message_text("Ses oluşturulurken bir hata oluştu.")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN çevre değişkeni bulunamadı!")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot polling modunda ve web sunucu ile baslatiliyor...")
    app.run_polling()

if __name__ == '__main__':
    main()
