import calendar
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_calendar(year: int = None, month: int = None):
    now = datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month

    month_name = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", 
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month-1]
    
    keyboard = []
    keyboard.append([InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore")])
    
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"calendar_day:{year}-{month:02d}-{day:02d}"))
        keyboard.append(row)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # Навигация: Года и Месяцы
    keyboard.append([
        InlineKeyboardButton(text="⏪ год", callback_data=f"calendar_nav:{year-1}-{month}", style="primary"),
        InlineKeyboardButton(text="⬅️ мес", callback_data=f"calendar_nav:{prev_year}-{prev_month}", style="primary"),
        InlineKeyboardButton(text="мес ➡️", callback_data=f"calendar_nav:{next_year}-{next_month}", style="primary"),
        InlineKeyboardButton(text="год ⏩", callback_data=f"calendar_nav:{year+1}-{month}", style="primary")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)