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

# ===== НАСТРОЙКИ ВРЕМЕНИ (НОВОСИБИРСК GMT+7) =====
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

# ===== КЛАВИАТУРА =====
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать конкурс")],
            [KeyboardButton(text="📋 Мои конкурсы")],
            [KeyboardButton(text="📢 Мои каналы/чаты")],
            [KeyboardButton(text="🆘 Служба поддержки")]
        ],
        resize_keyboard=True
    )

# ===== СОСТОЯНИЯ FSM =====
class CreateRaffle(StatesGroup):
    waiting_post = State()
    waiting_button_text = State()
    waiting_channels = State()
    waiting_winners_count = State()
    waiting_publish_channel = State()
    waiting_publish_date = State()
    waiting_end_type = State()
    waiting_end_date = State()
    waiting_end_participants = State()

class BroadcastStates(StatesGroup):
    waiting_text = State()

class AdminPickStates(StatesGroup):
    waiting_raffle_id = State()
    waiting_winners_count = State()

# ===== КОМАНДА ОТМЕНЫ =====
@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Действие отменено.", reply_markup=main_keyboard())

# ===== УВЕДОМЛЕНИЕ ПРИ ЗАПУСКЕ =====
async def send_start_notification():
    try:
        now = get_now()
        await bot.send_message(
            ADMIN_ID,
            f"✅ <b>Бот giveawayrnd_bot запущен!</b>\n\n"
            f"📅 Время (Новосибирск): {format_datetime(now)}\n"
            f"📊 Конкурсов в БД: {len(raffles)}\n"
            f"🤖 Бот работает 24/7!\n\n"
            f"📢 Наш бот: @giveawayrnd_bot",
            parse_mode="HTML"
        )
    except:
        pass

# ===== /start =====
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎲 <b>GiveawayRND</b>\n\n"
        "Бот для проведения конкурсов с проверкой подписки!\n\n"
        "🔹 <b>Создать конкурс</b> — бот задаст вопросы.\n"
        "🔹 <b>Мои конкурсы</b> — список твоих конкурсов.\n"
        "🔹 <b>Мои каналы/чаты</b> — добавленные каналы.\n"
        "🔹 <b>Служба поддержки</b> — помощь.\n\n"
        "⏳ <b>Время Новосибирское (GMT+7)</b>\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

# ===== ОБРАБОТЧИКИ КНОПОК =====
@dp.message(F.text == "📝 Создать конкурс")
async def create_raffle_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📝 <b>Создание конкурса</b>\n\n"
        "Отправьте текст для конкурса.\n"
        "Вы можете также отправить вместе с текстом картинку, видео или GIF.\n"
        "📌 Вы можете использовать только <b>1 медиафайл</b>\n\n"
        "Бот для проведения конкурсов полностью бесплатный и прозрачный.\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_post)

@dp.message(F.text == "📋 Мои конкурсы")
async def my_raffles_button(message: Message):
    my = [r for r in raffles.values() if r.get("creator") == message.from_user.id]
    if not my:
        await message.answer("📭 У тебя нет конкурсов.", reply_markup=main_keyboard())
        return
    text = "📋 <b>Мои конкурсы</b>\n\n"
    for r in my:
        status = {"active": "✅ Активен", "finished": "🏁 Завершён", "draft": "📝 Черновик"}.get(r.get("status"), r.get("status"))
        text += f"📢 {r.get('publish_channel', 'неизвестно')}\n"
        text += f"   👥 Участников: {len(r.get('participants', []))}\n"
        text += f"   ❗️ Статус: {status}\n"
        if r.get("winner"):
            text += f"   🏆 Победитель: @{r['winner']['username']}\n"
        text += "\n"
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())

@dp.message(F.text == "📢 Мои каналы/чаты")
async def my_channels_button(message: Message):
    channels = user_channels.get(message.from_user.id, [])
    if not channels:
        await message.answer("📢 У тебя нет добавленных каналов.", reply_markup=main_keyboard())
        return
    text = "📢 <b>Мои каналы</b>\n\n"
    for ch in channels:
        text += f"✅ {ch}\n"
    text += f"\n📢 Наш бот: @giveawayrnd_bot"
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())

@dp.message(F.text == "🆘 Служба поддержки")
async def support_button(message: Message):
    await message.answer(
        "🆘 <b>Служба поддержки</b>\n\n"
        "По всем вопросам пишите: @your_support\n\n"
        "📌 Бот создан для проведения честных конкурсов.\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

# ===== СОЗДАНИЕ КОНКУРСА (ПОСТ) =====
@dp.message(CreateRaffle.waiting_post)
async def get_post(message: Message, state: FSMContext):
    media = None
    text = message.html_text or ""
    
    if message.photo:
        media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        media = {"type": "video", "file_id": message.video.file_id}
    elif message.animation:
        media = {"type": "animation", "file_id": message.animation.file_id}
    
    if not text and not media:
        await message.answer("❌ Отправь текст или текст + медиа!")
        return
    
    await state.update_data(text=text, media=media)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Свой текст", callback_data="custom_button")],
        [InlineKeyboardButton(text="🎯 Участвовать", callback_data="button_участвовать")],
        [InlineKeyboardButton(text="🔔 Принять участие", callback_data="button_принять_участие")],
        [InlineKeyboardButton(text="✅ Участвую!", callback_data="button_участвую")]
    ])
    
    await message.answer(
        "🔘 <b>Текст кнопки</b>\n\n"
        "Выберите готовый вариант или напишите свой.\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_button_text)

@dp.callback_query(F.data == "custom_button")
async def custom_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Напиши свой текст для кнопки:")
    await state.set_state(CreateRaffle.waiting_button_text)
    await callback.answer()

@dp.callback_query(F.data.startswith("button_"))
async def preset_button(callback: CallbackQuery, state: FSMContext):
    text = callback.data.split("_")[1].replace("_", " ")
    await state.update_data(button_text=text)
    await ask_channels(callback.message, state)
    await callback.answer()

@dp.message(CreateRaffle.waiting_button_text)
async def get_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text.strip())
    await ask_channels(message, state)

# ===== КАНАЛЫ =====
async def ask_channels(message: Message, state: FSMContext):
    user_id = message.from_user.id
    channels = user_channels.get(user_id, [])
    
    text = "📢 <b>Добавьте каналы</b>\n\n"
    if channels:
        text += "Добавленные каналы:\n"
        for ch in channels:
            text += f"✅ {ch}\n"
        text += "\n"
    
    text += (
        "1️⃣ Добавьте бота (@giveawayrnd_bot) в ваш канал как администратора.\n"
        "2️⃣ Отправьте боту канал в формате <code>@channelname</code>\n\n"
        "📌 Канал, в котором публикуете конкурс, добавлять <b>не нужно</b>.\n\n"
        "📢 Наш бот: @giveawayrnd_bot"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Достаточно каналов", callback_data="channels_done")]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(CreateRaffle.waiting_channels)

@dp.message(CreateRaffle.waiting_channels)
async def add_channel(message: Message, state: FSMContext):
    user_id = message.from_user.id
    channel = message.text.strip()
    
    if not channel.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @")
        return
    
    if user_id not in user_channels:
        user_channels[user_id] = []
    
    if channel in user_channels[user_id]:
        await message.answer(f"❌ Канал {channel} уже добавлен!")
        return
    
    try:
        member = await bot.get_chat_member(channel, bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer(f"❌ Бот не админ в {channel}!")
            return
    except:
        await message.answer(f"❌ Канал {channel} не найден!")
        return
    
    user_channels[user_id].append(channel)
    save_channels(user_id, user_channels[user_id])
    await message.answer(f"✅ Канал {channel} добавлен!\n\n📢 Наш бот: @giveawayrnd_bot")

@dp.callback_query(F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    channels = user_channels.get(user_id, [])
    await state.update_data(channels=channels)
    
    await callback.message.answer(
        "👥 <b>Сколько победителей?</b>\n\n"
        "Напишите число от 1 до 10.\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_winners_count)
    await callback.answer()

@dp.message(CreateRaffle.waiting_winners_count)
async def get_winners_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Напиши число!")
        return
    count = int(message.text)
    if count < 1 or count > 10:
        await message.answer("❌ От 1 до 10!")
        return
    await state.update_data(winners_count=count)
    
    await message.answer(
        "📢 <b>В каком канале публикуем?</b>\n\n"
        "Напишите название канала.\n"
        "Пример: <code>@my_channel</code>\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_publish_channel)

@dp.message(CreateRaffle.waiting_publish_channel)
async def get_publish_channel(message: Message, state: FSMContext):
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @")
        return
    await state.update_data(publish_channel=channel)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Прямо сейчас", callback_data="publish_now")],
        [InlineKeyboardButton(text="⏰ Запланировать", callback_data="publish_schedule")]
    ])
    
    await message.answer(
        "📅 <b>Когда публикуем?</b>\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_publish_date)

@dp.callback_query(F.data == "publish_now")
async def publish_now(callback: CallbackQuery, state: FSMContext):
    await state.update_data(publish_date=format_datetime(get_now()))
    await ask_end_type(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "publish_schedule")
async def publish_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Время публикации</b>\n\n"
        "Укажите время в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Примеры:\n"
        f"<code>{format_datetime(get_now() + timedelta(minutes=10))}</code> - через 10 минут\n"
        f"<code>{format_datetime(get_now() + timedelta(hours=1))}</code> - через час\n"
        f"<code>{format_datetime(get_now() + timedelta(days=1))}</code> - через день\n\n"
        "⏳ <b>Время Новосибирское (GMT+7)</b>\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_publish_date)
    await callback.answer()

@dp.message(CreateRaffle.waiting_publish_date)
async def get_publish_date(message: Message, state: FSMContext):
    dt = parse_datetime(message.text.strip())
    if dt is None:
        await message.answer("❌ Неправильный формат! Пример: <code>10.07.2026 15:00</code>", parse_mode="HTML")
        return
    if dt < get_now():
        await message.answer(f"❌ Дата должна быть в будущем! Сейчас {format_datetime(get_now())}")
        return
    await state.update_data(publish_date=message.text.strip())
    await ask_end_type(message, state)

async def ask_end_type(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ По времени", callback_data="end_time")],
        [InlineKeyboardButton(text="👥 По кол-ву участников", callback_data="end_participants")]
    ])
    await message.answer(
        "⏳ <b>Как завершить конкурс?</b>\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_end_type)

@dp.callback_query(F.data == "end_time")
async def end_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Дата завершения</b>\n\n"
        "Напишите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        f"⏳ Сейчас: {format_datetime(get_now())} (Новосибирск)\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_date)
    await callback.answer()

@dp.callback_query(F.data == "end_participants")
async def end_participants(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👥 <b>Кол-во участников</b>\n\n"
        "Напишите число — когда столько наберётся, конкурс завершится.\n\n"
        "📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_participants)
    await callback.answer()

@dp.message(CreateRaffle.waiting_end_date)
async def get_end_date(message: Message, state: FSMContext):
    dt = parse_datetime(message.text.strip())
    if dt is None:
        await message.answer("❌ Неправильный формат! Пример: <code>10.07.2026 15:00</code>", parse_mode="HTML")
        return
    if dt < get_now():
        await message.answer(f"❌ Дата должна быть в будущем! Сейчас {format_datetime(get_now())}")
        return
    await state.update_data(end_date=message.text.strip())
    await finish_raffle(message, state)

@dp.message(CreateRaffle.waiting_end_participants)
async def get_end_participants(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Напиши число!")
        return
    await state.update_data(end_participants=int(message.text))
    await finish_raffle(message, state)

# ===== ФИНИШ СОЗДАНИЯ =====
async def finish_raffle(message: Message, state: FSMContext):
    global raffle_counter, raffles
    data = await state.get_data()
    
    raffle_counter += 1
    raffle_data = {
        "creator": message.from_user.id,
        "text": data.get("text"),
        "media": data.get("media"),
        "button_text": data.get("button_text"),
        "channels": data.get("channels", []),
        "winners_count": data.get("winners_count"),
        "publish_channel": data.get("publish_channel"),
        "publish_date": data.get("publish_date"),
        "end_date": data.get("end_date"),
        "end_participants": data.get("end_participants"),
        "participants": [],
        "selected_winners": [],
        "winner": None,
        "status": "draft",
        "message_id": None,
        "chat_id": None,
        "announced": False
    }
    raffles[raffle_counter] = raffle_data
    save_raffle(raffle_counter, raffle_data)
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Сохранить конкурс", callback_data=f"save_raffle_{raffle_counter}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_raffle")]
    ])
    
    await message.answer(
        f"✅ <b>Конкурс готов!</b>\n\n"
        f"📝 Текст: {data.get('text', '')[:100]}...\n"
        f"👥 Победителей: {data.get('winners_count')}\n"
        f"📢 Канал: {data.get('publish_channel')}\n"
        f"⏳ Окончание: {data.get('end_date') or 'по участникам'}\n\n"
        f"⏳ Время Новосибирское (GMT+7)\n"
        f"🔘 Проверь всё и сохрани.\n\n"
        f"📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("save_raffle_"))
async def save_raffle_callback(callback: CallbackQuery):
    raffle_id = int(callback.data.split("_")[2])
    raffle = raffles.get(raffle_id)
    if not raffle:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    raffle["status"] = "active"
    save_raffle(raffle_id, raffle)
    await publish_raffle(callback.message, raffle_id)
    await callback.answer()

@dp.callback_query(F.data == "cancel_raffle")
async def cancel_raffle(callback: CallbackQuery):
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()

# ===== ПУБЛИКАЦИЯ В КАНАЛ =====
async def publish_raffle(message: Message, raffle_id: int):
    raffle = raffles[raffle_id]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=raffle["button_text"], callback_data=f"join_{raffle_id}")]
    ])
    text = raffle["text"]
    if raffle.get("channels"):
        text += "\n\n📢 <b>Подпишись на каналы:</b>\n"
        for ch in raffle["channels"]:
            text += f"🔹 {ch}\n"
    
    text += f"\n\n📢 Бот для конкурсов: @giveawayrnd_bot"
    
    try:
        if raffle.get("media"):
            if raffle["media"]["type"] == "photo":
                msg = await bot.send_photo(
                    chat_id=raffle["publish_channel"],
                    photo=raffle["media"]["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            elif raffle["media"]["type"] == "video":
                msg = await bot.send_video(
                    chat_id=raffle["publish_channel"],
                    video=raffle["media"]["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            elif raffle["media"]["type"] == "animation":
                msg = await bot.send_animation(
                    chat_id=raffle["publish_channel"],
                    animation=raffle["media"]["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            msg = await bot.send_message(
                chat_id=raffle["publish_channel"],
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
        raffle["message_id"] = msg.message_id
        raffle["chat_id"] = msg.chat.id
        save_raffle(raffle_id, raffle)
        await message.answer(f"✅ Конкурс опубликован в {raffle['publish_channel']}!\n\n📢 @giveawayrnd_bot")
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}")

# ===== УЧАСТИЕ В КОНКУРСЕ (КНОПКА) =====
@dp.callback_query(F.data.startswith("join_"))
async def join_raffle(callback: CallbackQuery):
    raffle_id = int(callback.data.split("_")[1])
    raffle = raffles.get(raffle_id)
    
    if not raffle:
        await callback.answer("❌ Конкурс не найден!", show_alert=True)
        return
    
    if raffle.get("status") != "active":
        await callback.answer("❌ Конкурс уже завершён!", show_alert=True)
        return
    
    # Проверка подписки на каналы
    for channel in raffle.get("channels", []):
        try:
            status = await bot.get_chat_member(channel, callback.from_user.id)
            if status.status in ["left", "kicked"]:
                await callback.answer(f"❌ Подпишись на {channel}!", show_alert=True)
                return
        except Exception as e:
            await callback.answer(f"⚠️ Ошибка проверки {channel}!", show_alert=True)
            return
    
    user_id = str(callback.from_user.id)
    username = callback.from_user.username or "без username"
    first_name = callback.from_user.first_name or "без имени"
    
    # Проверка, не участвует ли уже
    for p in raffle.get("participants", []):
        if p["user_id"] == user_id:
            await callback.answer("⚠️ Вы уже участвуете!", show_alert=False)
            return
    
    # Добавление участника
    raffle["participants"].append({
        "user_id": user_id,
        "username": username,
        "first_name": first_name
    })
    save_raffle(raffle_id, raffle)
    
    # Проверка завершения по участникам
    if raffle.get("end_participants") and len(raffle["participants"]) >= raffle["end_participants"]:
        await announce_winner(raffle_id, from_join=True)
    
    await callback.answer("✅ Вы участвуете в конкурсе!", show_alert=False)

# ===== АДМИН-ПАНЕЛЬ =====
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Неизвестная команда")
        return
    active = len([r for r in raffles.values() if r.get("status") == "active"])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Все конкурсы", callback_data="admin_all")],
        [InlineKeyboardButton(text="🎲 Выбрать победителей", callback_data="admin_pick")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])
    await message.answer(
        f"🔐 <b>Админ-панель giveawayrnd_bot</b>\n\n"
        f"📊 Всего конкурсов: {len(raffles)}\n"
        f"✅ Активных: {active}\n"
        f"⏳ Новосибирск (GMT+7)\n\n"
        f"📢 Наш бот: @giveawayrnd_bot",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "admin_all")
async def admin_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    if not raffles:
        await callback.message.answer("📭 Нет конкурсов.")
        await callback.answer()
        return
    text = "📊 <b>Все конкурсы</b>\n\n"
    for rid, r in raffles.items():
        text += f"#{rid}: {r.get('publish_channel', 'неизвестно')}\n"
        text += f"   👥 Участников: {len(r.get('participants', []))}\n"
        text += f"   ❗️ Статус: {r.get('status')}\n"
        if r.get("selected_winners"):
            text += f"   👑 Твой выбор: {len(r['selected_winners'])} победителей\n"
        if r.get("winner"):
            text += f"   🏆 Победитель: @{r['winner']['username']}\n"
        text += "\n"
    text += f"\n📢 Наш бот: @giveawayrnd_bot"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_pick")
async def admin_pick(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    active = [rid for rid, r in raffles.items() if r.get("status") == "active" and len(r.get("participants", [])) > 0]
    if not active:
        await callback.message.answer("❌ Нет активных конкурсов с участниками!")
        await callback.answer()
        return
    
    text = "🎲 <b>Выбери конкурс</b>\n\n"
    for rid in active:
        r = raffles[rid]
        text += f"#{rid}: {r.get('publish_channel', 'неизвестно')} — {len(r.get('participants', []))} участников\n"
    text += "\nНапиши номер конкурса:"
    
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(AdminPickStates.waiting_raffle_id)
    await callback.answer()

@dp.message(AdminPickStates.waiting_raffle_id)
async def admin_pick_raffle(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Напиши номер конкурса цифрой!")
        return
    
    raffle_id = int(message.text)
    raffle = raffles.get(raffle_id)
    
    if not raffle or raffle.get("status") != "active":
        await message.answer("❌ Конкурс не найден или уже завершён!")
        await state.clear()
        return
    
    if len(raffle.get("participants", [])) == 0:
        await message.answer("❌ Нет участников!")
        await state.clear()
        return
    
    await state.update_data(raffle_id=raffle_id)
    
    await message.answer(
        f"🎲 <b>Сколько победителей выбрать?</b>\n\n"
        f"Участников: {len(raffle['participants'])}\n"
        f"Напиши число от 1 до {min(10, len(raffle['participants']))}:"
    )
    await state.set_state(AdminPickStates.waiting_winners_count)

@dp.message(AdminPickStates.waiting_winners_count)
async def admin_pick_winners(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Напиши число!")
        return
    
    count = int(message.text)
    data = await state.get_data()
    raffle_id = data.get("raffle_id")
    raffle = raffles.get(raffle_id)
    
    if not raffle:
        await message.answer("❌ Конкурс не найден!")
        await state.clear()
        return
    
    participants = raffle.get("participants", [])
    if count < 1 or count > len(participants):
        await message.answer(f"❌ Введи число от 1 до {len(participants)}!")
        return
    
    # Выбираем победителей
    shuffled = participants.copy()
    random.shuffle(shuffled)
    winners = shuffled[:count]
    
    raffle["selected_winners"] = winners
    save_raffle(raffle_id, raffle)
    
    # Формируем сообщение
    if count == 1:
        w = winners[0]
        text = f"✅ <b>Ты выбрал:</b> @{w['username']} ({w['first_name']})\n\n📌 Он будет объявлен, когда конкурс завершится."
    else:
        text = f"✅ <b>Ты выбрал {count} победителей:</b>\n\n"
        for i, w in enumerate(winners, 1):
            text += f"{i}. @{w['username']} ({w['first_name']})\n"
        text += f"\n📌 Они будут объявлены, когда конкурс завершится."
    
    await message.answer(text, parse_mode="HTML")
    await state.clear()

# ===== РАССЫЛКА =====
@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    await callback.message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Отправь текст для рассылки всем пользователям.\n"
        "Можно использовать HTML-разметку.\n\n"
        "📢 @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_text)
    await callback.answer()

@dp.message(BroadcastStates.waiting_text)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = get_all_users()
    if not users:
        await message.answer("❌ Нет пользователей для рассылки.")
        await state.clear()
        return
    
    sent = 0
    failed = 0
    
    for user_id in users:
        try:
            await bot.send_message(
                user_id,
                message.html_text + "\n\n📢 @giveawayrnd_bot",
                parse_mode="HTML"
            )
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}\n\n"
        f"📢 @giveawayrnd_bot",
        parse_mode="HTML"
    )
    await state.clear()

# ===== ОБЪЯВЛЕНИЕ ПОБЕДИТЕЛЯ =====
async def announce_winner(raffle_id: int, from_join: bool = False):
    raffle = raffles.get(raffle_id)
    if not raffle or raffle.get("announced"):
        return
    
    if raffle.get("selected_winners"):
        winners = raffle["selected_winners"]
    else:
        if not raffle.get("participants"):
            return
        participants = raffle["participants"]
        count = min(raffle.get("winners_count", 1), len(participants))
        shuffled = participants.copy()
        random.shuffle(shuffled)
        winners = shuffled[:count]
    
    raffle["winner"] = winners[0] if winners else None
    raffle["status"] = "finished"
    raffle["announced"] = True
    save_raffle(raffle_id, raffle)
    
    # Меняем кнопку
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Завершён", callback_data="finished")]
        ])
        await bot.edit_message_reply_markup(
            chat_id=raffle["chat_id"],
            message_id=raffle["message_id"],
            reply_markup=keyboard
        )
    except:
        pass
    
    # Формируем сообщение
    if len(winners) == 1:
        w = winners[0]
        text = f"🎉 <b>КОНКУРС ЗАВЕРШЁН!</b>\n\n🏆 Победитель: @{w['username']} ({w['first_name']})\n\nПоздравляем! 🎊"
    else:
        text = f"🎉 <b>КОНКУРС ЗАВЕРШЁН!</b>\n\n🏆 <b>Победители:</b>\n"
        for i, w in enumerate(winners, 1):
            text += f"{i}. @{w['username']} ({w['first_name']})\n"
        text += f"\nПоздравляем! 🎊"
    
    try:
        await bot.send_message(
            chat_id=raffle["chat_id"],
            text=text + f"\n\n📢 Бот для конкурсов: @giveawayrnd_bot",
            parse_mode="HTML"
        )
    except:
        pass
    
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ <b>Победители объявлены!</b>\n\n#{raffle_id}: {raffle.get('publish_channel')}\n{text[:200]}",
            parse_mode="HTML"
        )
    except:
        pass

# ===== ФОНОВАЯ ПРОВЕРКА ВРЕМЕНИ =====
async def check_raffles_time():
    while True:
        now = get_now().timestamp()
        for raffle_id, raffle in raffles.items():
            if raffle.get("status") == "active" and raffle.get("end_date") and not raffle.get("announced"):
                dt = parse_datetime(raffle["end_date"])
                if dt is None:
                    continue
                if now >= dt.timestamp():
                    await announce_winner(raffle_id)
        await asyncio.sleep(60)

# ===== ЗАПУСК =====
async def main():
    print(f"🤖 Бот giveawayrnd_bot запущен! Время Новосибирское (GMT+7): {format_datetime(get_now())}")
    await bot.delete_webhook(drop_pending_updates=True)
    await send_start_notification()
    asyncio.create_task(check_raffles_time())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
