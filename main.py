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

BOT_TOKEN = "8769346438:AAGwRDxzGszAVmRhAT8z7pFfaRCJDi6jHzU"

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

# ===========================
# /start
# ===========================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🎲 <b>Добро пожаловать в Randomazer!</b>\n\n"
        "Здесь проходят розыгрыши с автоматическим выбором победителей.\n\n"
        "Чтобы участвовать — нажмите кнопку ниже!",
        reply_markup=main_menu
    )


# ===========================
# /admin
# ===========================

@dp.message(Command("admin"))
async def admin(message: Message):

    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Неизвестная команда")
        return

    await message.answer(
        f"🔐 <b>Админ-панель Randomazer</b>\n\n"
        f"👥 Участников: <b>{users_count()}</b>",
        reply_markup=admin_menu
    )


# ===========================
# УЧАСТВОВАТЬ
# ===========================

@dp.callback_query(F.data == "join")
async def join(callback: CallbackQuery):

    user = callback.from_user

    cursor.execute(
        "SELECT user_id FROM participants WHERE user_id=?",
        (str(user.id),)
    )

    if cursor.fetchone():

        await callback.answer(
            "Вы уже участвуете!",
            show_alert=True
        )

        return

    cursor.execute(
        """
        INSERT INTO participants
        VALUES(?,?,?)
        """,
        (
            str(user.id),
            user.username,
            user.first_name
        )
    )

    db.commit()

    await callback.answer(
        "Регистрация успешна!",
        show_alert=True
    )

    await callback.message.answer(
        "✅ Вы зарегистрированы в розыгрыше Randomazer!\n\n"
        "🍀 Ждите объявления победителей!"
    )


# ===========================
# НЕИЗВЕСТНЫЕ КОМАНДЫ
# ===========================

@dp.message()
async def unknown(message: Message):
    await message.answer("❌ Неизвестная команда")

# ===========================
# СПИСОК УЧАСТНИКОВ
# ===========================

@dp.callback_query(F.data == "list")
async def list_users(callback: CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    cursor.execute("""
    SELECT user_id, username, first_name
    FROM participants
    """)

    users = cursor.fetchall()

    if not users:
        await callback.message.answer(
            "❌ Нет участников."
        )
        return

    text = "📋 <b>Участники розыгрыша</b>\n\n"

    number = 1

    for user_id, username, first_name in users:

        if username:
            name = f"@{username}"
        else:
            name = first_name

        text += (
            f"{number}. {name} "
            f"({first_name})\n"
            f"ID: <code>{user_id}</code>\n\n"
        )

        number += 1

    text += f"Всего: <b>{len(users)}</b>"

    await callback.message.answer(text)


# ===========================
# ОЧИСТКА
# ===========================

@dp.callback_query(F.data == "clear")
async def clear_users(callback: CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    cursor.execute("DELETE FROM participants")

    db.commit()

    await callback.message.answer(
        "✅ Список участников очищен!"
    )


# ===========================
# НАСТРОЙКА ПРИЗОВ
# ===========================

@dp.callback_query(F.data == "prizes")
async def prizes(callback: CallbackQuery, state: FSMContext):

    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminState.wait_prizes)

    await callback.message.answer(
        "Введите призы так:\n\n"
        "1 место: iPhone\n"
        "2 место: AirPods\n"
        "3 место: PowerBank"
    )


@dp.message(AdminState.wait_prizes)
async def save_prizes(message: Message, state: FSMContext):

    lines = message.text.split("\n")

    p1 = "Главный приз"
    p2 = "Второй приз"
    p3 = "Третий приз"

    try:

        if len(lines) >= 1:
            p1 = lines[0].split(":",1)[1].strip()

        if len(lines) >= 2:
            p2 = lines[1].split(":",1)[1].strip()

        if len(lines) >= 3:
            p3 = lines[2].split(":",1)[1].strip()

    except:
        await message.answer("❌ Неверный формат.")
        return

    cursor.execute("""
    UPDATE settings
    SET prize1=?,
        prize2=?,
        prize3=?
    WHERE id=1
    """,(p1,p2,p3))

    db.commit()

    await state.clear()

    await message.answer(
        "✅ Призы сохранены!"
    )

# ===========================
# ВЫБОР ПОБЕДИТЕЛЕЙ
# ===========================

@dp.callback_query(F.data == "choose")
async def choose(callback: CallbackQuery, state: FSMContext):

    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminState.wait_winners)

    await callback.message.answer(
        "Введите количество победителей (1-10):"
    )


@dp.message(AdminState.wait_winners)
async def winners(message: Message, state: FSMContext):

    try:
        count = int(message.text)
    except:
        await message.answer("Введите число от 1 до 10.")
        return

    if count < 1 or count > 10:
        await message.answer("Введите число от 1 до 10.")
        return

    cursor.execute("""
    SELECT user_id, username, first_name
    FROM participants
    """)

    users = cursor.fetchall()

    if len(users) == 0:
        await message.answer("❌ Нет участников для розыгрыша!")
        await state.clear()
        return

    if count > len(users):
        count = len(users)

    prize1, prize2, prize3 = get_prizes()

    winners = random.sample(users, count)

    medals = ["🥇", "🥈", "🥉"]

    prizes = [
        prize1,
        prize2,
        prize3
    ]

    text = "🎉 <b>РЕЗУЛЬТАТЫ РОЗЫГРЫША!</b>\n\n"

    for i, user in enumerate(winners):

        user_id, username, first_name = user

        if username:
            name = f"@{username}"
        else:
            name = first_name

        medal = medals[i] if i < 3 else "🏅"
        prize = prizes[i] if i < 3 else ""

        text += (
            f"{medal} <b>{i+1} место</b>\n"
            f"{name} ({first_name})\n"
        )

        if prize:
            text += f"🎁 {prize}\n"

        text += "\n"

    await message.answer(text)

    await state.clear()


# ===========================
# ЗАПУСК
# ===========================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
