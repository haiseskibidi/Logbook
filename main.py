import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from handlers import router
from database import init_db
import scheduler

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="remind", description="Создать напоминание"),
        BotCommand(command="reminders", description="Список напоминаний"),
        BotCommand(command="read", description="Записи в дневнике"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logging.basicConfig(level=logging.INFO)

    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден!")
        return

    # Инициализация бота
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Передаем объект бота в планировщик
    scheduler.set_bot(bot)
    scheduler.scheduler.start()

    # Инициализация базы данных и команд
    await init_db()
    await set_commands(bot)

    try:
        print("Бот запущен и готов к работе!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
