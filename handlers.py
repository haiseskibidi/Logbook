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
import scheduler
from calendar_utils import get_calendar

router = Router()

class RemindStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_text = State()

# --- Клавиатуры ---

def get_main_reply_keyboard():
    # Постоянная нижняя клавиатура с кнопками напоминаний
    keyboard = [
        [KeyboardButton(text="🔔 Напоминание"), KeyboardButton(text="📋 Список напоминаний")]
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
        "👋 *Добро пожаловать в твой личный менеджер напоминаний!*\n\n"
        "Я помогу тебе не забыть о важных делах.\n\n"
        "💡 _Совет: Просто отправь мне любое текстовое сообщение (например, «Позвонить маме»), чтобы быстро настроить напоминание на нужный день и время!_"
    )
    # Отправляем ОДНО сообщение с нижней клавиатурой
    await message.answer(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_main_reply_keyboard()
    )

# --- Обработка Reply-кнопок ---

@router.message(F.text == "🔔 Напоминание")
async def reply_remind(message: Message, state: FSMContext):
    await start_remind_cmd(message, state)

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
    
    # Если текст напоминания уже введен заранее
    data = await state.get_data()
    if 'remind_text' in data:
        remind_date = data['remind_date']
        remind_text = data['remind_text']
        try:
            from scheduler import tz
            run_time_naive = datetime.strptime(f"{remind_date} {selected_time}", "%Y-%m-%d %H:%M")
            run_time = tz.localize(run_time_naive)
            
            if run_time < datetime.now(tz):
                await callback.message.edit_text("⚠️ Это время уже в прошлом! Попробуйте снова или выберите другую дату/время.")
                await callback.answer()
                return
                
            scheduler.schedule_reminder(callback.message.chat.id, run_time, remind_text)
            await callback.message.edit_text(
                f"✅ *Напоминание готово!*\n\n📅 `{remind_date}` 🕒 `{selected_time}`\n📝 {remind_text}",
                parse_mode="Markdown"
            )
            await state.clear()
        except Exception as e:
            await callback.message.edit_text(f"❌ Ошибка: {e}")
            await state.clear()
        await callback.answer()
        return

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
        
        # Если текст напоминания уже введен заранее
        data = await state.get_data()
        if 'remind_text' in data:
            remind_date = data['remind_date']
            remind_text = data['remind_text']
            
            from scheduler import tz
            run_time_naive = datetime.strptime(f"{remind_date} {time_text}", "%Y-%m-%d %H:%M")
            run_time = tz.localize(run_time_naive)
            
            if run_time < datetime.now(tz):
                await message.answer("⚠️ Это время уже в прошлом! Попробуйте еще раз.")
                return
                
            scheduler.schedule_reminder(message.chat.id, run_time, remind_text)
            await message.answer(
                f"✅ *Напоминание готово!*\n\n📅 `{remind_date}` 🕒 `{time_text}`\n📝 {remind_text}",
                parse_mode="Markdown"
            )
            await state.clear()
            return

        await state.set_state(RemindStates.waiting_for_text)
        await message.answer(f"🕒 Время: *{time_text}*\n\n✍️ Введите текст напоминания:", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Неверный формат! Напишите время, например: `14:30`")

@router.message(RemindStates.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    data = await state.get_data()
    remind_date, remind_time = data['remind_date'], data['remind_time']
    try:
        from scheduler import tz
        run_time_naive = datetime.strptime(f"{remind_date} {remind_time}", "%Y-%m-%d %H:%M")
        run_time = tz.localize(run_time_naive)
        
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

@router.message(Command("reminders"))
async def list_reminders_cmd(message: Message):
    await show_reminders(message)

async def show_reminders(message: Message):
    text, kb = get_reminders_content(message.chat.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

def get_reminders_content(chat_id: int):
    jobs = scheduler.scheduler.get_jobs()
    user_jobs = [j for j in jobs if j.id.startswith(f"remind_{chat_id}_")]
    user_jobs = sorted(user_jobs, key=lambda j: j.next_run_time)

    if not user_jobs:
        return "У вас нет активных напоминаний. 📭", None

    response = "🔔 *Ваши активные напоминания:*\n\n"
    buttons = []
    current_row = []
    
    for idx, job in enumerate(user_jobs, 1):
        time_str = job.next_run_time.strftime("%d.%m.%Y %H:%M")
        text = job.args[1] if len(job.args) > 1 else "Без текста"
        response += f"{idx}️⃣ ⏰ `{time_str}` — {text}\n"
        
        btn = InlineKeyboardButton(text=f"❌ {idx}", callback_data=f"del_remind|{job.id}")
        current_row.append(btn)
        
        if len(current_row) == 4:
            buttons.append(current_row)
            current_row = []
            
    if current_row:
        buttons.append(current_row)

    buttons.append([InlineKeyboardButton(text="🗑 Очистить всё", callback_data="clear_confirm", style="danger")])
    return response, InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data.startswith("del_remind|"))
async def delete_single_reminder_cb(callback: CallbackQuery):
    job_id = callback.data.split("|")[1]
    job = scheduler.scheduler.get_job(job_id)
    if job:
        job.remove()
        await callback.answer("✅ Напоминание удалено.")
    else:
        await callback.answer("⚠️ Напоминание уже удалено или не существует.", show_alert=True)
        
    text, kb = get_reminders_content(callback.message.chat.id)
    if kb is None:
        await callback.message.edit_text(text, reply_markup=None)
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "clear_confirm")
async def clear_confirm_cb(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    for job in scheduler.scheduler.get_jobs():
        if job.id.startswith(f"remind_{chat_id}_"): job.remove()
    await callback.message.edit_text("✅ Все напоминания удалены. 📭")
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

# --- Авто-напоминания из текста ---

@router.message(F.text & ~F.text.startswith('/'))
async def text_reminder_handler(message: Message, state: FSMContext):
    menu_buttons = {"🔔 Напоминание", "📋 Список напоминаний"}
    if message.text in menu_buttons:
        return 
        
    await state.set_state(RemindStates.waiting_for_date)
    await state.update_data(remind_text=message.text)
    
    await message.answer(
        f"✍️ Текст напоминания: *\"{message.text}\"*\n\n📅 Выберите дату на календаре:",
        parse_mode="Markdown",
        reply_markup=get_calendar()
    )