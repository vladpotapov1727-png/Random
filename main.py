import os
import asyncio
import random
import sqlite3
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message, CallbackQuery
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ===== ВЕБ-СЕРВЕР =====
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 Бот giveawayrnd_bot работает 24/7!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

# ===== НАСТРОЙКИ ВРЕМЕНИ =====
NEWSIB_TIMEZONE = ZoneInfo('Asia/Novosibirsk')

def get_now():
    return datetime.now(NEWSIB_TIMEZONE)

def format_datetime(dt):
    return dt.strftime("%d.%m.%Y %H:%M")

def parse_datetime(date_str):
    try:
        date_str = date_str.strip()
        dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        return dt.replace(tzinfo=NEWSIB_TIMEZONE)
    except ValueError:
        return None

# ===== НАСТРОЙКИ БОТА =====
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден!")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ADMIN_ID = 7197233783
SUPPORT_TAG = "@Tonalkasupport"

# ===== БАЗА ДАННЫХ =====
DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raffle_id INTEGER UNIQUE,
            creator_id INTEGER,
            text TEXT,
            media TEXT,
            button_text TEXT,
            channels TEXT,
            winners_count INTEGER,
            publish_channel TEXT,
            publish_date TEXT,
            end_date TEXT,
            end_participants INTEGER,
            participants TEXT,
            selected_winners TEXT,
            winner TEXT,
            status TEXT,
            announced INTEGER DEFAULT 0,
            message_id INTEGER,
            chat_id INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel TEXT,
            UNIQUE(user_id, channel)
        )
    """)
    conn.commit()
    conn.close()

def save_raffle(raffle_id, data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO raffles (
            raffle_id, creator_id, text, media, button_text, channels,
            winners_count, publish_channel, publish_date, end_date,
            end_participants, participants, selected_winners, winner,
            status, announced, message_id, chat_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        raffle_id,
        data.get("creator"),
        data.get("text"),
        json.dumps(data.get("media")),
        data.get("button_text"),
        json.dumps(data.get("channels", [])),
        data.get("winners_count"),
        data.get("publish_channel"),
        data.get("publish_date"),
        data.get("end_date"),
        data.get("end_participants"),
        json.dumps(data.get("participants", [])),
        json.dumps(data.get("selected_winners", [])),
        json.dumps(data.get("winner")),
        data.get("status"),
        1 if data.get("announced") else 0,
        data.get("message_id"),
        data.get("chat_id")
    ))
    conn.commit()
    conn.close()

def load_raffles():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raffles")
    rows = cursor.fetchall()
    conn.close()
    raffles = {}
    for row in rows:
        raffle_id = row[1]
        raffles[raffle_id] = {
            "creator": row[2],
            "text": row[3],
            "media": json.loads(row[4]) if row[4] else None,
            "button_text": row[5],
            "channels": json.loads(row[6]) if row[6] else [],
            "winners_count": row[7],
            "publish_channel": row[8],
            "publish_date": row[9],
            "end_date": row[10],
            "end_participants": row[11],
            "participants": json.loads(row[12]) if row[12] else [],
            "selected_winners": json.loads(row[13]) if row[13] else [],
            "winner": json.loads(row[14]) if row[14] else None,
            "status": row[15],
            "announced": bool(row[16]),
            "message_id": row[17],
            "chat_id": row[18]
        }
    return raffles

def save_channels(user_id, channels):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_channels WHERE user_id = ?", (user_id,))
    for ch in channels:
        cursor.execute("INSERT INTO user_channels (user_id, channel) VALUES (?, ?)", (user_id, ch))
    conn.commit()
    conn.close()

def load_channels(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT channel FROM user_channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def load_all_channels():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, channel FROM user_channels")
    rows = cursor.fetchall()
    conn.close()
    channels = {}
    for user_id, channel in rows:
        if user_id not in channels:
            channels[user_id] = []
        channels[user_id].append(channel)
    return channels

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT creator_id FROM raffles")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# ===== ИНИЦИАЛИЗАЦИЯ =====
init_db()
raffles = load_raffles()
user_channels = load_all_channels()
raffle_counter = max(raffles.keys()) if raffles else 0

# ===== КЛАВ
