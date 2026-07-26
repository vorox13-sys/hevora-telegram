import os

# Telegram Bot Token ve API Anahtarları
BOT_TOKEN = os.getenv("BOT_TOKEN", "BURAYA_TELEGRAM_BOT_TOKEN_YAZ")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "BURAYA_OPENROUTER_KEY_YAZ")

# Edge TTS için Varsayılan Ses Ayarları (Örn: Türkçe Kadın veya Erkek sesi)
DEFAULT_VOICE = "tr-TR-AhmetNeural" # Alternatif: "tr-TR-EmelNeural"
