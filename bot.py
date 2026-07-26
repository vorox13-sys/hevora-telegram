import json
import os
import threading
import requests
from flask import Flask, request as flask_request
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
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# --- FLASK SUNUCU VE WEBHOOK ---
web_app = Flask(__name__)
telegram_app = None

@web_app.route('/')
def home():
    return "Hevora Nano Bot aktif ve Webhook modunda çalışıyor! 🚀"

@web_app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook_handler():
    if telegram_app:
        try:
            update_data = flask_request.get_json(force=True)
            update = Update.de_json(update_data, telegram_app.bot)
            
            async def process():
                async with telegram_app:
                    await telegram_app.process_update(update)
                    
            import asyncio
            asyncio.run(process())
        except Exception as e:
            print(f"Webhook işleme hatası: {e}")
    return "ok", 200

def run_flask():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)
# -------------------------

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

MODELS_LIST = [
    "deepseek/deepseek-chat:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "microsoft/phi-3-medium-128k-instruct:free"
]

SYSTEM_PROMPT = """
Sen Hevora Nano'sun. Hevora Labs tarafından geliştirilmiş gelişmiş bir yapay zeka asistanısın.
Her zaman Türkçe cevap ver.
Kısa, doğal, profesyonel ve doğru konuş.
"""

MEMORY_FILE = "memory.json"
CREDITS_FILE = "credits.json"
INITIAL_CREDITS = 50

if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        conversation_history = json.load(f)
else:
    conversation_history = {}

if os.path.exists(CREDITS_FILE):
    with open(CREDITS_FILE, "r", encoding="utf-8") as f:
        user_credits = json.load(f)
else:
    user_credits = {}

def save_credits():
    with open(CREDITS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_credits, f, ensure_ascii=False, indent=2)

def check_and_use_credit(user_id):
    user_id = str(user_id)
    if user_id not in user_credits:
        user_credits[user_id] = INITIAL_CREDITS
    
    if user_credits[user_id] <= 0:
        return False
    
    user_credits[user_id] -= 1
    save_credits()
    return True

def ask_ai(chat_id, user_message):
    chat_id = str(chat_id)
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    history = conversation_history[chat_id]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    last_error = None
    answer = None

    for model in MODELS_LIST:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 3000,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                break
            else:
                last_error = response.text
        except Exception as e:
            last_error = str(e)
            continue

    if not answer and gemini_client:
        try:
            full_prompt = f"Sistem Talimatı: {SYSTEM_PROMPT}\n\n"
            for h in history:
                role = "Kullanıcı" if h["role"] == "user" else "Asistan"
                full_prompt += f"{role}: {h['content']}\n"
            full_prompt += f"Kullanıcı: {user_message}"

            gemini_response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_prompt
            )
            if gemini_response and gemini_response.text:
                answer = gemini_response.text
        except Exception as gemini_err:
            last_error = f"OpenRouter Hatası: {last_error} | Gemini Hatası: {str(gemini_err)}"

    if not answer:
        raise Exception(f"Tüm servisler denendi, yanıt alınamadı. Son hata: {last_error}")

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})

    conversation_history[chat_id] = history[-20:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=2)

    return answer

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_credits:
        user_credits[user_id] = INITIAL_CREDITS
        save_credits()

    await update.message.reply_text(
        f"👋 Merhaba!\n\n"
        f"Ben **Hevora Nano**, **Hevora Labs** tarafından geliştirildim.\n"
        f"💳 Kalan Krediniz: **{user_credits[user_id]}**\n\n"
        "Bana metin, görsel veya PDF dosyası gönderebilirsin.",
        parse_mode="Markdown"
    )

async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    current = user_credits.get(user_id, INITIAL_CREDITS)
    await update.message.reply_text(f"💳 Kalan Kredi Miktarınız: **{current}**", parse_mode="Markdown")

async def add_credit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Kullanım: /addcredit <user_id> <miktar>")
        return
    
    target_user = context.args[0]
    try:
        amount = int(context.args[1])
        if target_user not in user_credits:
            user_credits[target_user] = INITIAL_CREDITS
        user_credits[target_user] += amount
        save_credits()
        await update.message.reply_text(f"✅ Başarılı! {target_user} ID'li kullanıcıya {amount} kredi eklendi.")
    except ValueError:
        await update.message.reply_text("⚠️ Miktar sayısal olmalıdır.")

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
    user_id = update.effective_user.id
    if not check_and_use_credit(user_id):
        await update.message.reply_text("⚠️ Krediniz tükenmiştir!")
        return

    text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        answer = ask_ai(update.effective_chat.id, text)
        parts, mode = format_response(answer)
        
        keyboard = [
            [
                InlineKeyboardButton("🔊 Sesli Dinle", callback_data="tts_play"),
                InlineKeyboardButton("🖼 Fotoğraf Oluştur", callback_data="action_image")
            ],
            [
                InlineKeyboardButton("📄 PDF Oluştur", callback_data="action_pdf"),
                InlineKeyboardButton("👍 Doğru", callback_data="feedback_true"),
                InlineKeyboardButton("👎 Yanlış", callback_data="feedback_false")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for i, part in enumerate(parts):
            markup = reply_markup if i == len(parts) - 1 else None
            await update.message.reply_text(
                part, parse_mode=mode, disable_web_page_preview=True, reply_markup=markup
            )
    except Exception as e:
        print(f"Arka plan hatası: {e}")
        await update.message.reply_text("⚠️ Servislerde geçici bir yoğunluk oluştu, lütfen tekrar deneyin.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_and_use_credit(user_id):
        await update.message.reply_text("⚠️ Krediniz tükenmiştir!")
        return

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
    user_id = update.effective_user.id
    if not check_and_use_credit(user_id):
        await update.message.reply_text("⚠️ Krediniz tükenmiştir!")
        return

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
    data = query.data

    if data == "tts_play":
        target_text = query.message.text or "Sesli yanıt."
        audio_file = await text_to_speech(target_text)
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, "rb") as voice:
                await context.bot.send_voice(chat_id=query.message.chat_id, voice=voice)
            os.remove(audio_file)
        else:
            await query.edit_message_text("Ses oluşturulurken hata oluştu.")
    elif data == "action_image":
        target_text = query.message.text or "Hevora AI"
        prompt = target_text[:100]
        url = (
            "https://image.pollinations.ai/prompt/"
            + requests.utils.quote(prompt)
            + "?model=flux&width=1024&height=1024&nologo=true"
        )
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=url, caption="🎨 Üretilen görsel.")
    elif data == "action_pdf":
        target_text = query.message.text or "Rapor"
        pdf_filename = "hevora_rapor.txt"
        with open(pdf_filename, "w", encoding="utf-8") as f:
            f.write(target_text)
        with open(pdf_filename, "rb") as doc:
            await context.bot.send_document(chat_id=query.message.chat_id, document=doc, filename="Hevora_Yanit.txt")
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)
    elif data == "feedback_true":
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="❤️ Teşekkürler!")
    elif data == "feedback_false":
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="🛠 Geri bildiriminiz alındı.")

def main():
    global telegram_app
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN çevre değişkeni bulunamadı!")

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CallbackQueryHandler(button_handler))
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("credits", credits_command))
    telegram_app.add_handler(CommandHandler("addcredit", add_credit_admin))
    telegram_app.add_handler(CommandHandler("image", image))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.strip('/')}/{BOT_TOKEN}"
        import asyncio
        async def setup_webhook():
            await telegram_app.initialize()
            await telegram_app.bot.set_webhook(url=webhook_url)
        asyncio.run(setup_webhook())
        print(f"Webhook ayarlandı ve uygulama başlatıldı: {webhook_url}")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    import time
    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()
