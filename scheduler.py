from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from aiogram import Bot
from datetime import datetime
import os
from pytz import timezone

# Глобальная переменная для хранения экземпляра бота
_bot: Bot = None

# Получаем таймзону из окружения или по умолчанию Владивосток
TIMEZONE_NAME = os.getenv("TIMEZONE", "Asia/Vladivostok")
tz = timezone(TIMEZONE_NAME)

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.db')
}

# Инициализируем планировщик с конкретной таймзоной
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=tz)

def set_bot(bot: Bot):
    global _bot
    _bot = bot

async def send_reminder(chat_id: int, text: str):
    # Используем глобальный объект бота для отправки
    if _bot:
        try:
            await _bot.send_message(chat_id, f"🕒 *Напоминание!*\n\n{text}", parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки напоминания: {e}")

def schedule_reminder(chat_id: int, run_time: datetime, text: str):
    # Если run_time без часового пояса, APScheduler интерпретирует его в своей таймзоне
    job_id = f"remind_{chat_id}_{int(run_time.timestamp())}"
    # Передаем только простые типы данных (int и str), которые легко сохраняются в БД
    scheduler.add_job(
        send_reminder,
        trigger='date',
        run_date=run_time,
        args=[chat_id, text],
        id=job_id,
        replace_existing=True
    )