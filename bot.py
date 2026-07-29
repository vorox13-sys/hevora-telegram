import json
import os
import threading
import time
import random
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
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Admin ID'lerini .env üzerinden virgülle ayrılmış şekilde alıyoruz (Örn: ADMIN_IDS="123456789,987654321")
ADMIN_IDS = [int(aid.strip()) for aid in os.getenv("ADMIN_IDS", "").split(",") if aid.strip().isdigit()]

MODELS_LIST = [
    "deepseek/deepseek-chat",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemini-2.0-flash-exp:free"
]

# --- FLASK WEB SERVER (Render Port Kontrolü İçin) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Hevora Nano Bot aktif ve çalışıyor! 🚀"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)
# ----------------------------------------------------

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
Sen Hevora Nano'sun. Hevora Labs tarafından geliştirilmiş gelişmiş bir yapay zeka asistanısın.
Her zaman Türkçe cevap ver.
Kısa, doğal, profesyonel ve doğru konuş. Emojileri metin akışını bozmayacak şekilde dengeli ve düzgün kullan.
"""

MEMORY_FILE = "memory.json"
CREDITS_FILE = "credits.json"
BANS_FILE = "bans.json"
INITIAL_CREDITS = 50

# Veri dosyalarını yükleme / oluşturma
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

if os.path.exists(BANS_FILE):
    with open(BANS_FILE, "r", encoding="utf-8") as f:
        banned_users = json.load(f)
else:
    banned_users = []

def save_credits():
    with open(CREDITS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_credits, f, ensure_ascii=False, indent=2)

def save_bans():
    with open(BANS_FILE, "w", encoding="utf-8") as f:
        json.dump(banned_users, f, ensure_ascii=False, indent=2)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def check_and_use_credit(user_id):
    user_id_str = str(user_id)
    if user_id_str not in user_credits:
        user_credits[user_id_str] = INITIAL_CREDITS
    
    if user_credits[user_id_str] <= 0:
        return False
    
    user_credits[user_id_str] -= 1
    save_credits()
    return True

def ask_ai(chat_id, user_message):
    chat_id = str(chat_id)
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    history = conversation_history[chat_id]
    answer = None
    last_error = None

    # 1. ÖNCE GEMİNİ DENENİR (Otomatik tekrar deneme mekanizmasıyla)
    if gemini_client:
        for attempt in range(2):
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
                    break
            except Exception as gemini_err:
                last_error = f"Gemini Hatası: {str(gemini_err)}"
                time.sleep(1)

    # 2. GEMİNİ YANIT VEREMEZSE OPENROUTER MODELLERİ YEDEK OLARAK DEVREYE GİRER
    if not answer and OPENROUTER_API_KEY:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

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
                        "max_tokens": 2000,
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

    if not answer:
        raise Exception(f"Tüm servisler yoğun. Son hata: {last_error}")

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})

    conversation_history[chat_id] = history[-20:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=2)

    return answer

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        await update.message.reply_text("⛔ Bu botu kullanma yetkiniz yasaklanmıştır.")
        return

    user_id_str = str(user_id)
    if user_id_str not in user_credits:
        user_credits[user_id_str] = INITIAL_CREDITS
        save_credits()

    await update.message.reply_text(
        f"👋 Merhaba!\n\n"
        f"Ben **Hevora Nano**, **Hevora Labs** tarafından geliştirildim.\n"
        f"💳 Kalan Krediniz: **{user_credits[user_id_str]}**\n\n"
        "Bana metin, görsel veya PDF dosyası gönderebilir, oyunlar oynayabilirsin! 🎮",
        parse_mode="Markdown"
    )

async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    current = user_credits.get(user_id, INITIAL_CREDITS)
    await update.message.reply_text(f"💳 Kalan Kredi Miktarınız: **{current}**", parse_mode="Markdown")

# --- GEMİNİ İLE GÖRSEL ÜRETİMİ ---
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if not check_and_use_credit(user_id):
        await update.message.reply_text("⚠️ Krediniz tükenmiştir!")
        return

    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Kullanım:\n/image astronot kedi")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    
    try:
        if not gemini_client:
            raise Exception("Gemini API anahtarı yapılandırılmamış.")
        
        # Gemini 2.5 Flash veya Imagen model desteği ile görsel üretim promptu
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Şu açıklama için bir görsel üretmek istiyorum, bana görseli oluşturacak en iyi ve detaylı İngilizce görsel üretim promptunu (sadece promptu) ver: {prompt}"
        )
        refined_prompt = response.text.strip() if response and response.text else prompt

        # Pollinations veya Imagen fallback entegrasyonu (Gemini görsel üretimi)
        image_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(refined_prompt)}?model=flux&width=1024&height=1024&nologo=true"
        await update.message.reply_photo(photo=image_url, caption=f"🎨 **Prompt:** {prompt}", parse_mode="Markdown")
    except Exception as e:
        print(f"Görsel üretim hatası: {e}")
        await update.message.reply_text("⚠️ Görsel üretilirken bir hata oluştu.")

# --- 4-5 TANE EĞLENCELİ OYUN SİSTEMİ ---
async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎲 Zar At", callback_data="game_dice"), InlineKeyboardButton("🎯 Dart At", callback_data="game_dart")],
        [InlineKeyboardButton("🪙 Yazı Tura", callback_data="game_coin"), InlineKeyboardButton("🎰 Şanslı Slot", callback_data="game_slot")],
        [InlineKeyboardButton("🔢 Sayı Tahmin", callback_data="game_guess")]
    ]
    await update.message.reply_text("🎮 **Oyun Salonu**\n\nOynamak istediğin oyunu seç:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_games_callback(query, data):
    chat_id = query.message.chat_id
    if data == "game_dice":
        dice = random.randint(1, 6)
        await query.message.reply_text(f"🎲 Zar attın ve gelen sayı: **{dice}**", parse_mode="Markdown")
    elif data == "game_dart":
        score = random.randint(1, 10)
        await query.message.reply_text(f"🎯 Dart tahtasına vurdun! Puanın: **{score}/10**", parse_mode="Markdown")
    elif data == "game_coin":
        result = random.choice(["Yazı 🦅", "Tura 👑"])
        await query.message.reply_text(f"🪙 Para atıldı: **{result}**", parse_mode="Markdown")
    elif data == "game_slot":
        slots = random.choice([("🍒", "🍒", "🍒"), ("🍋", "🍋", "🍋"), ("⭐", "⭐", "⭐"), ("💎", "7", "🍒")])
        if slots[0] == slots[1] == slots[2]:
            await query.message.reply_text(f"🎰 {slots[0]} {slots[1]} {slots[2]}\n\nTebrikler! **Büyük İkramiye!** 🎉", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"🎰 {slots[0]} {slots[1]} {slots[2]}\n\nMaalesef kazanamadın, tekrar dene!", parse_mode="Markdown")
    elif data == "game_guess":
        target = random.randint(1, 3)
        await query.message.reply_text(f"🔢 1 ile 3 arasında bir sayı tuttum. Tahminini doğrudan sohbete yazabilirsin (Örn: 2)")

# --- ADMIN PANELİ & KOMUTLARI ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return

    admin_text = (
        "🛠 **Hevora Admin Paneli**\n\n"
        "Kullanılabilir Komutlar:\n"
        "• `/stats` - Genel istatistikler\n"
        "• `/broadcast <mesaj>` - Herkese duyuru gönder\n"
        "• `/ban <user_id>` - Kullanıcıyı yasakla\n"
        "• `/unban <user_id>` - Yasağı kaldır\n"
        "• `/addcredit <user_id> <miktar>` - Kredi tanımla\n"
        "• `/users` - Kullanıcı sayısını göster"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return
    total_users = len(user_credits)
    total_banned = len(banned_users)
    await update.message.reply_text(f"📊 **Bot İstatistikleri**\n\n• Toplam Kullanıcı: {total_users}\n• Yasaklı Kullanıcı: {total_banned}", parse_mode="Markdown")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Kullanım: /broadcast <mesaj>")
        return
    
    count = 0
    for uid_str in user_credits.keys():
        try:
            await context.bot.send_message(chat_id=int(uid_str), text=f"📢 **Duyuru:**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"✅ Duyuru {count} kullanıcıya başarıyla gönderildi.")

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return
    if not context.args:
        await update.message.reply_text("Kullanım: /ban <user_id>")
        return
    try:
        uid = int(context.args[0])
        if uid not in banned_users:
            banned_users.append(uid)
            save_bans()
        await update.message.reply_text(f"🚫 {uid} ID'li kullanıcı yasaklandı.")
    except ValueError:
        await update.message.reply_text("Geçersiz User ID.")

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return
    if not context.args:
        await update.message.reply_text("Kullanım: /unban <user_id>")
        return
    try:
        uid = int(context.args[0])
        if uid in banned_users:
            banned_users.remove(uid)
            save_bans()
        await update.message.reply_text(f"✅ {uid} ID'li kullanıcının yasağı kaldırıldı.")
    except ValueError:
        await update.message.reply_text("Geçersiz User ID.")

async def add_credit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu komutu kullanma yetkiniz yok.")
        return
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

# --- MESAJ VE CHAT YÖNETİCİLERİ ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
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
                InlineKeyboardButton("🖼 Görsel Üret", callback_data="action_image")
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
        await update.message.reply_text("⚠️ Servis yanıt verirken yoğunluk oluştu, lütfen tekrar deneyin.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users or not check_and_use_credit(user_id):
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
    if user_id in banned_users or not check_and_use_credit(user_id):
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

    if data.startswith("game_"):
        await handle_games_callback(query, data)
        return

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
        image_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?model=flux&width=1024&height=1024&nologo=true"
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=image_url, caption="🎨 Üretilen görsel.")
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
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN çevre değişkeni bulunamadı!")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CallbackQueryHandler(button_handler))
    # Eski halleri (İngilizce) yerine bunları yaz:
    application.add_handler(CommandHandler("baslat", start))          # Eskisi: "start" idi
    application.add_handler(CommandHandler("kredi", credits))        # Eskisi: "credits" idi
    application.add_handler(CommandHandler("oyun", game))            # Eskisi: "game" idi
    application.add_handler(CommandHandler("gorsel", image))          # Eskisi: "image" idi
    application.add_handler(CommandHandler("admin", admin_panel))    # Bu admin kalabilir veya türkçeleştirebilirsin
    application.add_handler(CommandHandler("istatistik", stats))     # Eskisi: "stats" idi
    application.add_handler(CommandHandler("duyuru", broadcast))     # Eskisi: "broadcast" idi
    application.add_handler(CommandHandler("yasakla", ban))          # Eskisi: "ban" idi
    application.add_handler(CommandHandler("yasak_kaldir", unban))   # Eskisi: "unban" idi
    application.add_handler(CommandHandler("kredi_ekle", addcredit)) # Eskisi: "addcredit" idi

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot ve Admin paneli polling modunda başlatılıyor...")
    application.run_polling()

if __name__ == '__main__':
    main()

