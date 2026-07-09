import asyncio
import sqlite3
import random
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ===========================
# НАСТРОЙКИ
# ===========================

BOT_TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН"

ADMIN_ID = 7197233783

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# ===========================
# БАЗА ДАННЫХ
# ===========================

db = sqlite3.connect("participants.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS participants(
    user_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings(
    id INTEGER PRIMARY KEY,
    prize1 TEXT,
    prize2 TEXT,
    prize3 TEXT
)
""")

cursor.execute("SELECT * FROM settings")

if cursor.fetchone() is None:
    cursor.execute("""
    INSERT INTO settings
    VALUES(
        1,
        'Главный приз',
        'Второй приз',
        'Третий приз'
    )
    """)

db.commit()


class AdminState(StatesGroup):
    wait_winners = State()
    wait_prizes = State()


main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎯 Участвовать в розыгрыше",
                callback_data="join"
            )
        ]
    ]
)

admin_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Список участников",
                callback_data="list"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎲 Выбрать победителей",
                callback_data="choose"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏆 Настроить призы",
                callback_data="prizes"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Очистить список",
                callback_data="clear"
            )
        ]
    ]
)


def users_count():
    cursor.execute("SELECT COUNT(*) FROM participants")
    return cursor.fetchone()[0]


def get_prizes():
    cursor.execute("SELECT prize1, prize2, prize3 FROM settings")
    return cursor.fetchone()
