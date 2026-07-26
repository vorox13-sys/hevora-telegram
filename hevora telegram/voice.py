import edge_tts
import os

async def text_to_speech(text: str, output_filename: str = "voice_response.mp3", voice: str = "tr-TR-AhmetNeural"):
    """Verilen metni Edge TTS kullanarak ses dosyasına dönüştürür."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_filename)
        return output_filename
    except Exception as e:
        print(f"Ses üretme hatası: {e}")
        return None
