import os
import edge_tts

async def text_to_speech(text, output_file="output.mp3"):
    try:
        voice = "tr-TR-AhmetNeural" 
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        return output_file
    except Exception as e:
        print(f"TTS Hatası: {e}")
        return None

async def button_handler(update, context):
    query = update.callback_query
    await query.answer() # Butondaki yükleniyor animasyonunu kapatır

    if query.data == "tts_play":
        # Butonun basıldığı mesajın metnini hedef metin olarak alıyoruz
        target_text = query.message.text or "Sesli yanıt."
        
        # Geçici ses dosyası oluştur
        audio_file = await text_to_speech(target_text)
        
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, "rb") as voice:
                await context.bot.send_voice(chat_id=query.message.chat_id, voice=voice)
            os.remove(audio_file) # Gönderildikten sonra dosyayı temizle
        else:
            await query.edit_message_text("Ses oluşturulurken bir hata oluştu.")
