import os
import asyncio
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument
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
    raise ValueError("BOT_TOKEN не найден!")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ADMIN_ID = 7197233783  # ТВОЙ ID

# ===== ДАННЫЕ =====
raffles = {}
raffle_counter = 0
user_channels = {}

# ===== СОСТОЯНИЯ FSM =====
class CreateRaffle(StatesGroup):
    waiting_text = State()
    waiting_media = State()
    waiting_button_text = State()
    waiting_channels = State()
    waiting_winners_count = State()
    waiting_publish_channel = State()
    waiting_publish_date = State()
    waiting_end_type = State()
    waiting_end_date = State()
    waiting_end_participants = State()

# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать конкурс", callback_data="create_raffle")],
        [InlineKeyboardButton(text="📋 Мои конкурсы", callback_data="my_raffles")],
        [InlineKeyboardButton(text="📢 Мои каналы", callback_data="my_channels")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ])
    await message.answer(
        "🎲 <b>Randomazer</b>\n\n"
        "Бот для проведения конкурсов с проверкой подписки!\n\n"
        "🔹 <b>Создать конкурс</b> — бот задаст вопросы.\n"
        "🔹 <b>Мои конкурсы</b> — список твоих конкурсов.\n"
        "🔹 <b>Мои каналы</b> — добавленные каналы.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ===== СОЗДАНИЕ КОНКУРСА =====
@dp.callback_query(F.data == "create_raffle")
async def create_raffle_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 <b>Создание конкурса</b>\n\n"
        "Отправь текст для конкурса.\n"
        "Можешь использовать разметку HTML:\n"
        "<code>&lt;b&gt;жирный&lt;/b&gt;</code>, <code>&lt;i&gt;курсив&lt;/i&gt;</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_text)
    await callback.answer()

@dp.message(CreateRaffle.waiting_text)
async def get_text(message: Message, state: FSMContext):
    await state.update_data(text=message.html_text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Добавить медиа", callback_data="add_media")],
        [InlineKeyboardButton(text="➡️ Без медиа", callback_data="no_media")]
    ])
    await message.answer(
        "📎 <b>Добавить медиа?</b>\n\n"
        "Можешь добавить картинку, видео или GIF.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_media)

@dp.callback_query(F.data == "add_media")
async def add_media(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📤 Отправь медиафайл (картинку, видео или GIF).\n\n"
        "📌 Только <b>один</b> файл.",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_media)
    await callback.answer()

@dp.callback_query(F.data == "no_media")
async def no_media(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media=None)
    await ask_button_text(callback.message, state)
    await callback.answer()

@dp.message(CreateRaffle.waiting_media)
async def get_media(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(media={"type": "photo", "file_id": message.photo[-1].file_id})
    elif message.video:
        await state.update_data(media={"type": "video", "file_id": message.video.file_id})
    elif message.animation:
        await state.update_data(media={"type": "animation", "file_id": message.animation.file_id})
    else:
        await message.answer("❌ Отправь картинку, видео или GIF!")
        return
    
    await ask_button_text(message, state)

async def ask_button_text(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Свой текст", callback_data="custom_button")],
        [InlineKeyboardButton(text="🎯 Участвовать", callback_data="button_участвовать")],
        [InlineKeyboardButton(text="🔔 Принять участие", callback_data="button_принять_участие")]
    ])
    await message.answer(
        "🔘 <b>Текст кнопки</b>\n\n"
        "Выбери готовый вариант или напиши свой.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CreateRaffle.waiting_button_text)

@dp.callback_query(F.data == "custom_button")
async def custom_button(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Напиши свой текст для кнопки:")
    await state.set_state(CreateRaffle.waiting_button_text)
    await callback.answer()

@dp.callback_query(F.data.startswith("button_"))
async def preset_button(callback: types.CallbackQuery, state: FSMContext):
    text = callback.data.split("_")[1].replace("_", " ")
    await state.update_data(button_text=text)
    await ask_channels(callback.message, state)
    await callback.answer()

@dp.message(CreateRaffle.waiting_button_text)
async def get_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text.strip())
    await ask_channels(message, state)

async def ask_channels(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    
    channels = user_channels.get(user_id, [])
    text = "📢 <b>Добавь каналы для подписки</b>\n\n"
    
    if channels:
        text += "Добавленные каналы:\n"
        for ch in channels:
            text += f"✅ {ch}\n"
        text += "\n"
    
    text += (
        "1️⃣ Добавь бота в канал как администратора.\n"
        "2️⃣ Отправь боту канал в формате <code>@channelname</code>\n"
        "3️⃣ Или перешли сообщение из канала.\n\n"
        "📌 Канал, в котором публикуешь конкурс, добавлять <b>не нужно</b>."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Достаточно каналов", callback_data="channels_done")]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(CreateRaffle.waiting_channels)

@dp.message(CreateRaffle.waiting_channels)
async def add_channel(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if text.startswith("@"):
        channel = text
    else:
        channel = text
    
    if user_id not in user_channels:
        user_channels[user_id] = []
    
    if channel in user_channels[user_id]:
        await message.answer(f"❌ Канал {channel} уже добавлен!")
        return
    
    # Проверяем, есть ли бот в канале
    try:
        chat = await bot.get_chat(channel)
        member = await bot.get_chat_member(channel, bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer(f"❌ Бот не админ в {channel}! Добавь бота в канал.")
            return
    except:
        await message.answer(f"❌ Не могу найти канал {channel}. Проверь название.")
        return
    
    user_channels[user_id].append(channel)
    await message.answer(f"✅ Канал {channel} добавлен! Можешь добавить ещё или нажать «Достаточно каналов».")

@dp.callback_query(F.data == "channels_done")
async def channels_done(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    channels = user_channels.get(user_id, [])
    await state.update_data(channels=channels)
    
    await callback.message.answer(
        "👥 <b>Сколько победителей?</b>\n\n"
        "Напиши число от 1 до 10.",
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
        "Напиши название канала, куда опубликовать пост.\n"
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
async def publish_now(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(publish_date=datetime.now())
    await ask_end_type(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "publish_schedule")
async def publish_schedule(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Время публикации</b>\n\n"
        "Напиши дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>23.07.2026 14:00</code>\n\n"
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
        await state.update_data(publish_date=date)
        await ask_end_type(message, state)
    except:
        await message.answer("❌ Неправильный формат! Пример: <code>23.07.2026 14:00</code>", parse_mode="HTML")

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
async def end_time(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📅 <b>Дата завершения</b>\n\n"
        "Напиши дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_date)
    await callback.answer()

@dp.callback_query(F.data == "end_participants")
async def end_participants(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👥 <b>Кол-во участников</b>\n\n"
        "Напиши число — когда столько участников наберётся, конкурс завершится.",
        parse_mode="HTML"
    )
    await state.set_state(CreateRaffle.waiting_end_participants)
    await callback.answer()

@dp.message(CreateRaffle.waiting_end_date)
async def get_end_date(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        data = await state.get_data()
        publish_date = data.get("publish_date")
        if date < publish_date:
            await message.answer("❌ Дата завершения должна быть позже публикации!")
            return
        await state.update_data(end_date=date)
        await finish_raffle(message, state)
    except:
        await message.answer("❌ Неправильный формат! Пример: <code>23.07.2026 14:00</code>", parse_mode="HTML")

@dp.message(CreateRaffle.waiting_end_participants)
async def get_end_participants(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Напиши число!")
        return
    await state.update_data(end_participants=int(message.text))
    await finish_raffle(message, state)

async def finish_raffle(message: Message, state: FSMContext):
    global raffle_counter, raffles
    
    data = await state.get_data()
    
    raffle_counter += 1
    raffles[raffle_counter] = {
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
        "winner": None,
        "status": "draft",
        "message_id": None,
        "chat_id": None
    }
    
    await state.clear()
    
    # Показываем превью
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Сохранить конкурс", callback_data=f"save_raffle_{raffle_counter}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_raffle")]
    ])
    
    await message.answer(
        f"✅ <b>Конкурс готов!</b>\n\n"
        f"📝 Текст: {data.get('text')[:100]}...\n"
        f"👥 Победителей: {data.get('winners_count')}\n"
        f"📢 Канал: {data.get('publish_channel')}\n"
        f"⏳ Окончание: {data.get('end_date') or 'по участникам'}\n\n"
        f"🔘 Проверь всё и сохрани.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("save_raffle_"))
async def save_raffle(callback: types.CallbackQuery):
    raffle_id = int(callback.data.split("_")[2])
    raffle = raffles.get(raffle_id)
    
    if not raffle:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    raffle["status"] = "active"
    
    # Публикуем
    await publish_raffle(callback.message, raffle_id)
    await callback.answer()

@dp.callback_query(F.data == "cancel_raffle")
async def cancel_raffle(callback: types.CallbackQuery):
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()

async def publish_raffle(message: Message, raffle_id: int):
    raffle = raffles[raffle_id]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=raffle["button_text"], callback_data=f"join_{raffle_id}")]
    ])
    
    text = raffle["text"]
    if raffle["channels"]:
        text += "\n\n📢 <b>Подпишись на каналы:</b>\n"
        for ch in raffle["channels"]:
            text += f"🔹 {ch}\n"
    
    try:
        if raffle["media"]:
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
            else:
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
        await message.answer(f"✅ Конкурс опубликован в {raffle['publish_channel']}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}")

# ===== УЧАСТИЕ =====
@dp.callback_query(F.data.startswith("join_"))
async def join_raffle(callback: types.CallbackQuery):
    raffle_id = int(callback.data.split("_")[1])
    raffle = raffles.get(raffle_id)
    
    if not raffle or raffle["status"] != "active":
        await callback.answer("❌ Конкурс уже завершён!", show_alert=True)
        return
    
    # Проверка подписки на все каналы
    for channel in raffle["channels"]:
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
    
    for p in raffle["participants"]:
        if p["user_id"] == user_id:
            await callback.answer("⚠️ Вы уже участвуете!", show_alert=False)
            return
    
    raffle["participants"].append({
        "user_id": user_id,
        "username": username,
        "first_name": first_name
    })
    
    # Проверка завершения по участникам
    if raffle.get("end_participants") and len(raffle["participants"]) >= raffle["end_participants"]:
        raffle["status"] = "finished"
        await auto_finish(raffle_id)
    
    await callback.answer("✅ Вы участвуете в конкурсе!", show_alert=False)

async def auto_finish(raffle_id: int):
    raffle = raffles[raffle_id]
    if not raffle["winner"]:
        winner = random.choice(raffle["participants"])
        raffle["winner"] = winner
        
        try:
            await bot.send_message(
                chat_id=raffle["chat_id"],
                text=f"🎉 <b>КОНКУРС ЗАВЕРШЁН!</b>\n\n"
                     f"🏆 Победитель: @{winner['username']} ({winner['first_name']})\n\n"
                     f"Поздравляем! 🎊",
                parse_mode="HTML"
            )
        except:
            pass

# ===== АДМИН-ПАНЕЛЬ (СКРЫТАЯ) =====
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Неизвестная команда")
        return
    
    active = len([r for r in raffles.values() if r["status"] == "active"])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Все конкурсы", callback_data="admin_all")],
        [InlineKeyboardButton(text="🎲 Выбрать победителя", callback_data="admin_pick")]
    ])
    
    await message.answer(
        f"🔐 <b>Админ-панель</b>\n\n"
        f"📊 Всего конкурсов: {len(raffles)}\n"
        f"✅ Активных: {active}\n"
        f"👥 Твой ID: {message.from_user.id}",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "admin_all")
async def admin_all(callback: types.CallbackQuery):
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
        text += f"   👥 Участников: {len(r['participants'])}\n"
        text += f"   ❗️ Статус: {r['status']}\n"
        if r.get("winner"):
            text += f"   🏆 Победитель: @{r['winner']['username']}\n"
        text += "\n"
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_pick")
async def admin_pick(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    active = [rid for rid, r in raffles.items() if r["status"] == "active" and len(r["participants"]) > 0]
    
    if not active:
        await callback.message.answer("❌ Нет активных конкурсов с участниками!")
        await callback.answer()
        return
    
    text = "🎲 <b>Выбери конкурс</b>\n\n"
    for rid in active:
        r = raffles[rid]
        text += f"#{rid}: {r.get('publish_channel', 'неизвестно')} — {len(r['participants'])} участников\n"
    
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
    
    if not raffle or raffle["status"] != "active":
        await message.answer("❌ Конкурс не найден или уже завершён!")
        return
    
    if len(raffle["participants"]) == 0:
        await message.answer("❌ Нет участников!")
        return
    
    winner = random.choice(raffle["participants"])
    raffle["winner"] = winner
    raffle["status"] = "finished"
    
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
    
    await message.answer(
        f"🎉 <b>ПОБЕДИТЕЛЬ</b> 🎉\n\n"
        f"🏆 @{winner['username']} ({winner['first_name']})\n"
        f"🎁 Приз: {raffle.get('prizes', ['Главный приз'])[0]}\n\n"
        f"Поздравляем! 🎊",
        parse_mode="HTML"
    )
    
    # Оповещаем в канал
    try:
        await bot.send_message(
            chat_id=raffle["chat_id"],
            text=f"🎉 <b>КОНКУРС ЗАВЕРШЁН!</b>\n\n"
                 f"🏆 Победитель: @{winner['username']} ({winner['first_name']})\n\n"
                 f"Поздравляем! 🎊",
            parse_mode="HTML"
        )
    except:
        pass

# ===== МОИ КОНКУРСЫ =====
@dp.callback_query(F.data == "my_raffles")
async def my_raffles(callback: types.CallbackQuery):
    my = [r for r in raffles.values() if r["creator"] == callback.from_user.id]
    
    if not my:
        await callback.message.answer("📭 У тебя нет конкурсов.")
        await callback.answer()
        return
    
    text = "📋 <b>Мои конкурсы</b>\n\n"
    for r in my:
        status = {"active": "✅ Активен", "finished": "🏁 Завершён", "draft": "📝 Черновик"}.get(r["status"], r["status"])
        text += f"📢 {r.get('publish_channel', 'неизвестно')}\n"
        text += f"   👥 Участников: {len(r['participants'])}\n"
        text += f"   ❗️ Статус: {status}\n"
        if r.get("winner"):
            text += f"   🏆 Победитель: @{r['winner']['username']}\n"
        text += "\n"
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ===== МОИ КАНАЛЫ =====
@dp.callback_query(F.data == "my_channels")
async def my_channels(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    channels = user_channels.get(user_id, [])
    
    if not channels:
        await callback.message.answer(
            "📢 У тебя нет добавленных каналов.\n\n"
            "Чтобы добавить канал, создай конкурс — бот попросит добавить каналы."
        )
        await callback.answer()
        return
    
    text = "📢 <b>Мои каналы</b>\n\n"
    for ch in channels:
        text += f"✅ {ch}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")]
    ])
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "add_channel")
async def add_channel(callback: types.CallbackQuery):
    await callback.message.answer(
        "📢 Отправь название канала в формате <code>@channelname</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message()
async def handle_add_channel(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.startswith("@"):
        return
    
    if user_id not in user_channels:
        user_channels[user_id] = []
    
    if text in user_channels[user_id]:
        await message.answer(f"❌ Канал {text} уже добавлен!")
        return
    
    try:
        chat = await bot.get_chat(text)
        member = await bot.get_chat_member(text, bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer(f"❌ Бот не админ в {text}!")
            return
    except:
        await message.answer(f"❌ Канал {text} не найден!")
        return
    
    user_channels[user_id].append(text)
    await message.answer(f"✅ Канал {text} добавлен!")

# ===== ПОДДЕРЖКА =====
@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    await callback.message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "По всем вопросам пиши: @your_support\n\n"
        "📌 Бот создан для проведения честных конкурсов.",
        parse_mode="HTML"
    )
    await callback.answer()

# ===== ЗАПУСК =====
async def main():
    print("🤖 Бот Randomazer запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
