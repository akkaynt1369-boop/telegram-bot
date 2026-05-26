import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import asyncio
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import boto3
from botocore.config import Config

# ================== ВСТАВЬТЕ ВАШИ ДАННЫЕ ==================
BOT_TOKEN = "8801223775:AAEM8J_Ip-uEhVvba9P3DsARsnXyyakwR4U"   # Токен от @BotFather (новый, если старый скомпрометирован)

R2_ACCOUNT_ID = "5cfa2fdd7dfd7957d6c663c9ed0de2e4"           # Из правого нижнего угла Cloudflare
R2_ACCESS_KEY_ID = "0cac9f513feb0c298725e4f8db4e59dc"        # 32 символа, который вы проверили
R2_SECRET_ACCESS_KEY = "bf876addc66197d48fbad659d9263e37fb3ce7ab777ada82fc9b60111fe207b5"                     # ПОЛНЫЙ секретный ключ (скопируйте из Cloudflare)
R2_BUCKET_NAME = "mystillfots"                               # Название вашего бакета
R2_PUBLIC_URL = "https://pub-509a306816994714a761c583f2788500.r2.dev"  # URL после включения Public Access
# ==========================================================

# Буфер для альбомов (чтобы несколько фото в одном сообщении объединять)
album_buffer = defaultdict(lambda: {"photos": [], "caption": "", "timer": None})

# Клиент для загрузки в R2
s3_client = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4"),
    region_name="auto"
)

async def upload_to_r2(file_data, filename):
    try:
        s3_client.put_object(Bucket=R2_BUCKET_NAME, Key=filename, Body=file_data)
        return f"{R2_PUBLIC_URL}/{filename}"
    except Exception as e:
        print(f"Ошибка загрузки в R2: {e}")
        return None

async def handle_photo(update: Update, context):
    media_group_id = update.message.media_group_id
    caption = update.message.caption or ""

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_data = await file.download_as_bytearray()

    filename = f"{update.effective_user.id}_{photo.file_id}.jpg"
    r2_url = await upload_to_r2(file_data, filename)
    if not r2_url:
        await update.message.reply_text("Ошибка загрузки фото. Попробуйте позже.")
        return

    # Если одиночное фото
    if not media_group_id:
        await update.message.reply_text(f"{r2_url}\n\n{caption}")
        return

    # Альбом: собираем фото, отправляем одно сообщение через 2 секунды
    album = album_buffer[media_group_id]
    album["photos"].append(r2_url)
    if caption and not album["caption"]:
        album["caption"] = caption

    if album["timer"]:
        album["timer"].cancel()

    async def send_album():
        if media_group_id in album_buffer:
            photos = album_buffer[media_group_id]["photos"]
            cap = album_buffer[media_group_id]["caption"]
            numbered = "\n".join([f"{i+1}) {p}" for i, p in enumerate(photos)])
            result = f"{numbered}\n\n{cap}" if cap else numbered
            await update.message.reply_text(result)
            del album_buffer[media_group_id]

    loop = asyncio.get_event_loop()
    timer = loop.call_later(2, lambda: asyncio.create_task(send_album()))
    album["timer"] = timer

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("Бот запущен с R2. Ожидание фото...")
    app.run_polling()

if __name__ == "__main__":
    main()