import ssl
import os
import random
import string
import asyncio
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import boto3
from botocore.config import Config

# Отключаем проверку SSL (если нужно)
ssl._create_default_https_context = ssl._create_unverified_context

# ========== Чтение переменных окружения ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "mystillfots")   # по умолчанию ваш бакет
# Короткий домен (если не задан, используем длинный публичный URL)
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-509a306816994714a761c583f2788500.r2.dev")

# Проверка обязательных переменных
if not all([BOT_TOKEN, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
    raise ValueError("Не заданы необходимые переменные окружения: BOT_TOKEN, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")

# ========== Функция генерации короткого имени ==========
def generate_short_name(ext="jpg"):
    """Генерирует случайное имя файла из 13 букв/цифр"""
    chars = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    short = ''.join(random.choices(chars, k=13))
    return f"{short}.{ext}"

# ========== Настройка клиента R2 ==========
s3_client = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4"),
    region_name="auto"
)

# ========== Загрузка файла в R2 ==========
async def upload_to_r2(file_data, filename):
    try:
        s3_client.put_object(Bucket=R2_BUCKET_NAME, Key=filename, Body=file_data)
        return f"{R2_PUBLIC_URL}/{filename}"
    except Exception as e:
        print(f"Ошибка загрузки в R2: {e}")
        return None

# ========== Буфер для альбомов ==========
album_buffer = defaultdict(lambda: {"photos": [], "caption": "", "timer": None})

# ========== Обработчик фото ==========
async def handle_photo(update: Update, context):
    media_group_id = update.message.media_group_id
    caption = update.message.caption or ""

    # Получаем самое качественное фото
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_data = await file.download_as_bytearray()

    # Генерируем короткое уникальное имя (13 символов)
    filename = generate_short_name()

    # Загружаем в R2
    r2_url = await upload_to_r2(file_data, filename)
    if not r2_url:
        await update.message.reply_text("Ошибка загрузки фото. Попробуйте позже.")
        return

    # Если одиночное фото
    if not media_group_id:
        await update.message.reply_text(f"{r2_url}\n\n{caption}")
        return

    # Альбом: собираем все фото
    album = album_buffer[media_group_id]
    album["photos"].append(r2_url)
    if caption and not album["caption"]:
        album["caption"] = caption

    # Отменяем старый таймер, если есть
    if album["timer"]:
        album["timer"].cancel()

    # Устанавливаем новый таймер на 2 секунды
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

# ========== Запуск бота ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("Бот запущен с R2. Короткие имена (13 символов). Ожидание фото...")
    app.run_polling()

if __name__ == "__main__":
    main()
