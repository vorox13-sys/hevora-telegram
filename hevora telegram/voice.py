import os

async def button_handler(update, context):
    query = update.callback_query
    await query.answer() # Butondaki yükleniyor animasyonunu kapatır

    if query.data == "tts_play":
        # Kullanıcının son aldığı yanıtı veya metni buradan alabilirsin
        # Örnek test metni:
        target_text = "Sesli dinleme isteğiniz işleniyor." 
        
        # Geçici ses dosyası oluştur
        audio_file = await text_to_speech(target_text)
        
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, "rb") as voice:
                await context.bot.send_voice(chat_id=query.message.chat_id, voice=voice)
            os.remove(audio_file) # Gönderildikten sonra dosyayı temizle
        else:
            await query.edit_message_text("Ses oluşturulurken bir hata oluştu.")
