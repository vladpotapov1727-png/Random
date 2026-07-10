import os
import asyncio
import random
import sqlite3
import json
from datetime import datetime, timedelta
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

# ===== ВЕБ-СЕРВЕР ДЛЯ HEALTH CHECK =====
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 Бот Randomazer работает 24/7!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Добавь его в переменные окружения.")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ADMIN_ID = 7197233783  # ТВОЙ ID

# ===== БАЗА ДАННЫХ SQLITE =====
DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица розыгрышей
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
            selected_winner TEXT,
            winner TEXT,
            status TEXT,
            announced INTEGER DEFAULT 0,
            message_id INTEGER,
            chat_id INTEGER
        )
    """)
    
    # Таблица каналов пользователей
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
            end_participants, participants, selected_winner, winner,
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
        json.dumps(data.get("selected_winner")),
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
            "selected_winner": json.loads(row[13]) if row[13] else None,
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

# ===== КЛАВИАТУРА (ВНИЗУ) =====
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

# ===== УВЕДОМЛЕНИЕ ПРИ ЗАПУСКЕ =====
async def send_start_notification():
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✅ <b>Бот Randomazer запущен!</b>\n\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"📊 Конкурсов в БД: {len(raffles)}\n"
            f"🤖 Бот работает 24/7!",
            parse_mode="HTML"
        )
    except:
        pass

# ===== /start =====
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🎲 <b>Randomazer</b>\n\n"
        "Бот для проведения конкурсов с проверкой подписки!\n\n"
        "🔹 <b>Создать конкурс</b> — бот задаст вопросы.\n"
        "🔹 <b>Мои конкурсы</b> — список твоих конкурсов.\n"
        "🔹 <b>Мои каналы/чаты</b> — добавленные каналы.\n"
        "🔹 <b>Служба поддержки</b> — помощь.",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

# ===== ОБРАБОТЧИКИ КНОПОК (ВНИЗУ) =====
@dp.message(F.text == "📝 Создать конкурс")
async def create_raffle_button(message: Message, state: FSMContext):
    await message.answer(
        "📝 <b>Создание конкурса</b>\n\n"
        "Отправьте текст для конкурса.\n"
        "Вы можете также отправить вместе с текстом картинку, видео или GIF.\n"
        "📌 Вы можете использовать только <b>1 медиафайл</b>\n\n"
        "Бот для проведения конкурсов полностью бесплатный и прозрачный, ему будет приятно, "
        "если в конкурсном посте Вы укажите на него ссылку, спасибо.\n"
        "@Randomazery_bot",
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
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())

@dp.message(F.text == "🆘 Служба поддержки")
async def support_button(message: Message):
    await message.answer(
        "🆘 <b>Служба поддержки</b>\n\n"
        "По всем вопросам пишите: @your_support\n\n"
        "📌 Бот создан для проведения честных конкурсов.",
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
        "Выберите готовый вариант или напишите свой.",
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

# ===== КАНАЛЫ ДЛЯ ПОДПИСКИ =====
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
        "1️⃣ Добавьте бота (@Randomazery_bot) в ваш канал как администратора.\n"
        "2️⃣ Отправьте боту канал в формате <code>@channelname</code>\n\n"
        "📌 Канал, в котором публикуете конкурс, добавлять <b>не нужно</b>."
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
    await message.answer(f"✅ Канал {channel} добавлен!")

@dp.callback_query(F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    channels = user_channels.get(user_id, [])
    await state.update_data(channels=channels)
    
    await callback.message.answer(
        "👥 <b>Сколько победителей?</b>\n\n"
        "Напишите число от 1 до 10.",
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
        "Пример: <code>@my_channel</code>",
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
        "📅 <b>Когда публикуем?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_publish_date)

@dp.callback_query(F.data == "publish_now")
async def publish_now(callback: CallbackQuery, state: FSMContext):
    await state.update_data(publish_date=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    await ask_end_type(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "publish_schedule")
async def publish_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Время публикации</b>\n\n"
        "Укажите время в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Примеры:\n"
        "<code>09.07.2026 22:11</code> - через 10 минут\n"
        "<code>10.07.2026 22:01</code> - через день\n\n"
        "⏳ Бот живет по времени <b>Москва (GMT+3)</b>",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_publish_date)
    await callback.answer()

@dp.message(CreateRaffle.waiting_publish_date)
async def get_publish_date(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        if date < datetime.now():
            await message.answer("❌ Дата должна быть в будущем!")
            return
        await state.update_data(publish_date=message.text.strip())
        await ask_end_type(message, state)
    except:
        await message.answer("❌ Неправильный формат! Пример: <code>10.07.2026 15:00</code>", parse_mode="HTML")

async def ask_end_type(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ По времени", callback_data="end_time")],
        [InlineKeyboardButton(text="👥 По кол-ву участников", callback_data="end_participants")]
    ])
    await message.answer(
        "⏳ <b>Как завершить конкурс?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_end_type)

@dp.callback_query(F.data == "end_time")
async def end_time(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Дата завершения</b>\n\n"
        "Напишите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_date)
    await callback.answer()

@dp.callback_query(F.data == "end_participants")
async def end_participants(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👥 <b>Кол-во участников</b>\n\n"
        "Напишите число — когда столько наберётся, конкурс завершится.",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_participants)
    await callback.answer()

@dp.message(CreateRaffle.waiting_end_date)
async def get_end_date(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        await state.update_data(end_date=message.text.strip())
        await finish_raffle(message, state)
    except:
        await message.answer("❌ Неправильный формат!")

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
        "selected_winner": None,
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
        f"🔘 Проверь всё и сохрани.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("save_raffle_"))
async def save_raffle(callback: CallbackQuery):
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
        await message.answer(f"✅ Конкурс опубликован в {raffle['publish_channel']}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}")

# ===== УЧАСТИЕ В КОНКУРСЕ =====
@dp.callback_query(F.data.startswith("join_"))
async def join_raffle(callback: CallbackQuery):
    raffle_id = int(callback.data.split("_")[1])
    raffle = raffles.get(raffle_id)
    if not raffle or raffle.get("status") != "active":
        await callback.answer("❌ Конкурс уже завершён!", show_alert=True)
        return
    
    # Проверка подписки
    for channel in raffle.get("channels", []):
        try:
            status = await bot.get_chat_member(channel, callback.from_user.id)
            if status.status in ["left", "kicked"]:
                await callback.answer(f"❌ Подпишись на {channel}!", show_alert=True)
                return
        except:
            await callback.answer(f"⚠️ Ошибка проверки {channel}!", show_alert=True)
            return
    
    user_id = str(callback.from_user.id)
    username = callback.from_user.username or "без username"
    first_name = callback.from_user.first_name or "без имени"
    
    for p in raffle.get("participants", []):
        if p["user_id"] == user_id:
            await callback.answer("⚠️ Вы уже участвуете!", show_alert=False)
            return
    
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

# ===== АДМИН-ПАНЕЛЬ (СКРЫТАЯ) =====
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Неизвестная команда")
        return
    active = len([r for r in raffles.values() if r.get("status") == "active"])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Все конкурсы", callback_data="admin_all")],
        [InlineKeyboardButton(text="🎲 Выбрать победителя", callback_data="admin_pick")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])
    await message.answer(
        f"🔐 <b>Админ-панель</b>\n\n"
        f"📊 Всего конкурсов: {len(raffles)}\n"
        f"✅ Активных: {active}",
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
        if r.get("selected_winner"):
            text += f"   👑 Твой выбор: @{r['selected_winner']['username']}\n"
        if r.get("winner"):
            text += f"   🏆 Победитель: @{r['winner']['username']}\n"
        text += "\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_pick")
async def admin_pick(callback: CallbackQuery):
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
    await callback.answer()

@dp.message()
async def handle_admin_pick(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.text.isdigit():
        return
    raffle_id = int(message.text)
    raffle = raffles.get(raffle_id)
    if not raffle or raffle.get("status") != "active":
        await message.answer("❌ Конкурс не найден или уже завершён!")
        return
    if len(raffle.get("participants", [])) == 0:
        await message.answer("❌ Нет участников!")
        return
    winner = random.choice(raffle["participants"])
    raffle["selected_winner"] = winner
    save_raffle(raffle_id, raffle)
    await message.answer(
        f"✅ <b>Ты выбрал:</b> @{winner['username']} ({winner['first_name']})\n\n"
        f"📌 Он будет объявлен, когда конкурс завершится.",
        parse_mode="HTML"
    )

# ===== РАССЫЛКА =====
@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    await callback.message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Отправь текст, который хотите разослать всем пользователям.\n"
        "Можно использовать HTML-разметку: <b>жирный</b>, <i>курсив</i>\n\n"
        "⚠️ Отправка может занять некоторое время.",
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
                message.html_text,
                parse_mode="HTML"
            )
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="HTML"
    )
    await state.clear()

# ===== ОБЪЯВЛЕНИЕ ПОБЕДИТЕЛЯ =====
async def announce_winner(raffle_id: int, from_join: bool = False):
    raffle = raffles.get(raffle_id)
    if not raffle or raffle.get("announced"):
        return
    
    if raffle.get("selected_winner"):
        winner = raffle["selected_winner"]
    else:
        if not raffle.get("participants"):
            return
        winner = random.choice(raffle["participants"])
    
    raffle["winner"] = winner
    raffle["status"] = "finished"
    raffle["announced"] = True
    save_raffle(raffle_id, raffle)
    
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
    
    try:
        await bot.send_message(
            chat_id=raffle["chat_id"],
            text=f"🎉 <b>КОНКУРС ЗАВЕРШЁН!</b>\n\n"
                 f"🏆 Победитель: @{winner['username']} ({winner['first_name']})\n\n"
                 f"🎁 Приз: {raffle.get('prizes', ['Главный приз'])[0]}\n\n"
                 f"Поздравляем! 🎊",
            parse_mode="HTML"
        )
    except:
        pass
    
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ <b>Победитель объявлен!</b>\n\n"
                 f"#{raffle_id}: {raffle.get('publish_channel')}\n"
                 f"🏆 @{winner['username']} ({winner['first_name']})\n"
                 f"{'✅ Твой выбор' if raffle.get('selected_winner') else '🎲 Случайный выбор'}",
            parse_mode="HTML"
        )
    except:
        pass

# ===== ФОНОВАЯ ПРОВЕРКА ВРЕМЕНИ =====
async def check_raffles_time():
    while True:
        now = datetime.now().timestamp()
        for raffle_id, raffle in raffles.items():
            if raffle.get("status") == "active" and raffle.get("end_date") and not raffle.get("announced"):
                try:
                    end_date = datetime.strptime(raffle["end_date"], "%d.%m.%Y %H:%M").timestamp()
                    if now >= end_date:
                        await announce_winner(raffle_id)
                except:
                    pass
        await asyncio.sleep(60)

# ===== ЗАПУСК =====
async def main():
    print("🤖 Бот Randomazer запущен!")
    await send_start_notification()
    asyncio.create_task(check_raffles_time())
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
