from aiogram import Router, F, Bot
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from scheduler import tz
import database
import scheduler
from calendar_utils import get_calendar

router = Router()

class RemindStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_text = State()

# --- Клавиатуры ---

def get_main_reply_keyboard():
    # Постоянная нижняя клавиатура
    keyboard = [
        [KeyboardButton(text="📔 Написать в дневник"), KeyboardButton(text="🔔 Напоминание")],
        [KeyboardButton(text="📑 Просмотр записей"), KeyboardButton(text="📋 Список напоминаний")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_time_keyboard(page: int = 0):
    start_hour = 6 if page == 0 else 15
    end_hour = 15 if page == 0 else 24
    buttons = []
    current_row = []
    for hour in range(start_hour, end_hour):
        for minute in [0, 30]:
            t_str = f"{hour:02d}:{minute:02d}"
            current_row.append(InlineKeyboardButton(text=t_str, callback_data=f"time_select|{t_str}"))
            if len(current_row) == 4:
                buttons.append(current_row)
                current_row = []
    nav_row = []
    if page == 0:
        nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data="time_page|1", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="time_page|0", style="primary"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_remind", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Обработчики команд ---

@router.message(Command("start"))
async def start_cmd(message: Message):
    text = (
        "👋 *Добро пожаловать в твой личный дневник!*\n\n"
        "Я помогу тебе сохранять важные мысли и не забывать о делах.\n\n"
        "💡 _Совет: Просто отправь мне любое сообщение, чтобы сохранить его в дневник._"
    )
    # Отправляем ОДНО сообщение с нижней клавиатурой
    await message.answer(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_main_reply_keyboard()
    )

# --- Обработка Reply-кнопок ---

@router.message(F.text == "📔 Написать в дневник")
async def reply_diary(message: Message):
    await message.answer("Просто напиши мне текст сообщения, и я тут же сохраню его в твой дневник! ✍️")

@router.message(F.text == "🔔 Напоминание")
async def reply_remind(message: Message, state: FSMContext):
    await start_remind_cmd(message, state)

@router.message(F.text == "📑 Просмотр записей")
async def reply_read(message: Message):
    await show_diary_entries(message, message.from_user.id, datetime.now(tz).strftime("%Y-%m-%d"))

@router.message(F.text == "📋 Список напоминаний")
async def reply_reminders(message: Message):
    await show_reminders(message)

# --- Логика напоминаний ---

@router.message(Command("remind"))
async def start_remind_cmd(message: Message, state: FSMContext):
    await state.set_state(RemindStates.waiting_for_date)
    await message.answer("📅 Выберите дату на календаре:", reply_markup=get_calendar())

@router.callback_query(F.data.startswith("calendar_day:"))
async def process_calendar_day(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split(":")[1]
    chosen_dt = datetime.strptime(selected_date, "%Y-%m-%d")
    if chosen_dt.date() < datetime.now().date():
        return await callback.answer("⚠️ Нельзя выбрать дату в прошлом!", show_alert=True)
    await state.update_data(remind_date=selected_date)
    await state.set_state(RemindStates.waiting_for_time)
    await callback.message.edit_text(
        f"📅 Дата: *{selected_date}*\n\n🕒 Выберите время или введите своё (ЧЧ:ММ):",
        parse_mode="Markdown",
        reply_markup=get_time_keyboard(0)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("calendar_nav:"))
async def process_calendar_nav(callback: CallbackQuery):
    _, date_str = callback.data.split(":")
    year, month = map(int, date_str.split("-"))
    await callback.message.edit_reply_markup(reply_markup=get_calendar(year, month))
    await callback.answer()

@router.callback_query(F.data.startswith("time_select|"))
async def process_time_select(callback: CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("|")[1]
    await state.update_data(remind_time=selected_time)
    await state.set_state(RemindStates.waiting_for_text)
    await callback.message.edit_text(f"🕒 Время: *{selected_time}*\n\n✍️ Введите текст напоминания:", parse_mode="Markdown")
    await callback.answer()

@router.message(RemindStates.waiting_for_time)
async def process_time_manual(message: Message, state: FSMContext):
    time_text = message.text.strip()
    if len(time_text) == 4 and ":" in time_text:
        time_text = "0" + time_text
    try:
        datetime.strptime(time_text, "%H:%M")
        await state.update_data(remind_time=time_text)
        await state.set_state(RemindStates.waiting_for_text)
        await message.answer(f"🕒 Время: *{time_text}*\n\n✍️ Введите текст напоминания:", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Неверный формат! Напишите время, например: `14:30`")

@router.message(RemindStates.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    data = await state.get_data()
    remind_date, remind_time = data['remind_date'], data['remind_time']
    try:
        # Получаем объект таймзоны из планировщика
        from scheduler import tz
        
        # Создаем "наивный" объект времени
        run_time_naive = datetime.strptime(f"{remind_date} {remind_time}", "%Y-%m-%d %H:%M")
        # Делаем его "осведомленным" (aware) в нужной таймзоне
        run_time = tz.localize(run_time_naive)
        
        # Сравниваем с текущим временем в той же таймзоне
        if run_time < datetime.now(tz):
            return await message.answer("⚠️ Это время уже в прошлом!")
            
        scheduler.schedule_reminder(message.chat.id, run_time, message.text)
        await message.answer(
            f"✅ *Напоминание готово!*\n\n📅 `{remind_date}` 🕒 `{remind_time}`\n📝 {message.text}",
            parse_mode="Markdown"
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

# --- Просмотр и управление ---

@router.message(Command("read"))
async def read_cmd_handler(message: Message, command: CommandObject):
    date_str = command.args or datetime.now().strftime("%Y-%m-%d")
    await show_diary_entries(message, message.from_user.id, date_str)

async def show_diary_entries(message: Message, user_id: int, date_str: str):
    entries = await database.get_entries(user_id, date_str)
    if not entries:
        await message.answer(f"Записей за {date_str} не найдено. 😉")
    else:
        response = f"📅 *Твои записи за {date_str}:*\n\n"
        for date, content in entries:
            time_only = date.split()[1][:5]
            response += f"🔹 `{time_only}`: {content}\n"
        await message.answer(response, parse_mode="Markdown")

@router.message(Command("reminders"))
async def list_reminders_cmd(message: Message):
    await show_reminders(message)

async def show_reminders(message: Message):
    jobs = scheduler.scheduler.get_jobs()
    chat_id = message.chat.id
    user_jobs = [j for j in jobs if j.id.startswith(f"remind_{chat_id}_")]
    if not user_jobs:
        await message.answer("У вас нет активных напоминаний. 📭")
    else:
        response = "🔔 *Ваши активные напоминания:*\n\n"
        for job in user_jobs:
            time_str = job.next_run_time.strftime("%d.%m.%Y %H:%M")
            text = job.args[1] if len(job.args) > 1 else "Без текста"
            response += f"⏰ `{time_str}` — {text}\n"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Очистить всё", callback_data="clear_confirm", style="danger")]])
        await message.answer(response, parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "clear_confirm")
async def clear_confirm_cb(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    for job in scheduler.scheduler.get_jobs():
        if job.id.startswith(f"remind_{chat_id}_"): job.remove()
    await callback.message.edit_text("✅ Все напоминания удалены.")
    await callback.answer()

@router.callback_query(F.data == "cancel_remind")
async def cancel_remind_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()

@router.callback_query(F.data.startswith("time_page|"))
async def process_time_page(callback: CallbackQuery):
    page = int(callback.data.split("|")[1])
    await callback.message.edit_reply_markup(reply_markup=get_time_keyboard(page))
    await callback.answer()

# --- Дневник ---

@router.message(F.text & ~F.text.startswith('/'))
async def diary_entry_handler(message: Message):
    menu_buttons = {"📔 Написать в дневник", "🔔 Напоминание", "📑 Просмотр записей", "📋 Список напоминаний"}
    if message.text in menu_buttons:
        return 
    await database.add_entry(message.from_user.id, message.text)
    await message.answer("✅ Записал в твой дневник!")