import aiosqlite
from datetime import datetime
from scheduler import tz

DB_PATH = "diary.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS diary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL
            )
        """)
        await db.commit()

async def add_entry(user_id: int, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT INTO diary (date, content, user_id) VALUES (?, ?, ?)",
            (now, content, user_id)
        )
        await db.commit()

async def get_entries(user_id: int, date_str: str = None):
    if not date_str:
        date_str = datetime.now(tz).strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Search for entries starting with the date_str (YYYY-MM-DD)
        async with db.execute(
            "SELECT date, content FROM diary WHERE user_id = ? AND date LIKE ? ORDER BY date ASC",
            (user_id, f"{date_str}%")
        ) as cursor:
            return await cursor.fetchall()
