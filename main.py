import os
import asyncio
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ========== ДАННЫЕ ==========
ADMIN_ID = 7197233783  # ТВОЙ ID

# Все розыгрыши
raffles = {}  # {raffle_id: {"creator": user_id, "channel": "@channel", "end_date": timestamp, "prizes": [], "participants": [], "winner": None, "status": "active"}}
raffle_counter = 0

# Твои личные розыгрыши (как раньше)
my_raffles = {"participants": [], "is_running": False, "winner": None, "prizes": ["Главный приз", "Второй приз", "Третий приз"]}

# ========== КОМАНДА /start ==========
@dp.message(Command("start"))
async def start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Участвовать в розыгрыше", callback_data="join")],
        [InlineKeyboardButton(text="📋 Список розыгрышей", callback_data="list_raffles")],
        [InlineKeyboardButton(text="➕ Создать розыгрыш", callback_data="create_raffle")]
    ])
    await message.answer(
        "🎲 Добро пожаловать в Randomazer!\n\n"
        "🔹 Нажми 'Участвовать' — чтобы участвовать в текущем розыгрыше.\n"
        "🔹 Нажми 'Создать розыгрыш' — чтобы создать свой розыгрыш.\n"
        "🔹 Нажми 'Список розыгрышей' — чтобы увидеть все активные розыгрыши.\n\n"
        "📢 Подпишись на канал создателя, чтобы участвовать!",
        reply_markup=keyboard
    )

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Неизвестная команда")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои участники", callback_data="my_list")],
        [InlineKeyboardButton(text="🎲 Мои победители", callback_data="my_pick")],
        [InlineKeyboardButton(text="📊 Все розыгрыши", callback_data="all_raffles")],
        [InlineKeyboardButton(text="🗑 Очистить моих участников", callback_data="my_clear")]
    ])
    
    await message.answer(
        f"🔐 Админ-панель Randomazer\n\n"
        f"👥 Моих участников: {len(my_raffles['participants'])}\n"
        f"📊 Активных розыгрышей: {len([r for r in raffles.values() if r['status'] == 'active'])}",
        reply_markup=keyboard
    )

# ========== КНОПКА "УЧАСТВОВАТЬ" ==========
@dp.callback_query(F.data == "join")
async def join_my_raffle(callback: types.CallbackQuery):
    global my_raffles
    user_id = str(callback.from_user.id)
    username = callback.from_user.username or "без username"
    first_name = callback.from_user.first_name or "без имени"
    
    for p in my_raffles["participants"]:
        if p["user_id"] == user_id:
            await callback.answer("⚠️ Вы уже участвуете!", show_alert=False)
            return
    
    my_raffles["participants"].append({
        "user_id": user_id,
        "username": username,
        "first_name": first_name
    })
    
    await callback.answer("✅ Вы зарегистрированы!", show_alert=False)

# ========== СПИСОК РОЗЫГРЫШЕЙ ==========
@dp.callback_query(F.data == "list_raffles")
async def list_raffles(callback: types.CallbackQuery):
    active = [r for r in raffles.values() if r["status"] == "active"]
    
    if not active:
        await callback.message.answer("📭 Активных розыгрышей нет.")
        await callback.answer()
        return
    
    text = "📋 Активные розыгрыши:\n\n"
    for idx, r in enumerate(active, 1):
        creator = await bot.get_chat(r["creator"])
        text += f"{idx}. Создатель: @{creator.username or 'неизвестно'}\n"
        text += f"   📢 Канал: {r['channel']}\n"
        text += f"   👥 Участников: {len(r['participants'])}\n"
        text += f"   ⏳ До: {datetime.fromtimestamp(r['end_date']).strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await callback.message.answer(text)
    await callback.answer()

# ========== СОЗДАНИЕ РОЗЫГРЫША ==========
@dp.callback_query(F.data == "create_raffle")
async def create_raffle_start(callback: types.CallbackQuery):
    await callback.message.answer(
        "➕ Создание розыгрыша\n\n"
        "Введите данные в формате:\n"
        "Канал: @channel\n"
        "Дата: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Призы: 1 место: приз1, 2 место: приз2, 3 место: приз3\n\n"
        "Пример:\n"
        "@my_channel 10.07.2026 15:00 1 место: iPhone, 2 место: AirPods, 3 место: Сертификат"
    )
    await callback.answer()

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
@dp.message()
async def handle_text(message: types.Message):
    global raffle_counter, raffles
    
    if message.from_user.id == ADMIN_ID:
        # Обработка ввода для админа
        text = message.text.strip()
        if text.isdigit():
            # Выбор победителя для моего розыгрыша
            count = int(text)
            if 1 <= count <= 10 and len(my_raffles["participants"]) > 0:
                shuffled = my_raffles["participants"].copy()
                random.shuffle(shuffled)
                winners = shuffled[:count]
                
                result = "🎉 РЕЗУЛЬТАТЫ МОЕГО РОЗЫГРЫША!\n\n"
                for i, w in enumerate(winners, 1):
                    prize = my_raffles["prizes"][i-1] if i <= len(my_raffles["prizes"]) else f"{i} место"
                    result += f"🥇 {i} МЕСТО: @{w['username']} ({w['first_name']}) — {prize}\n"
                result += "\n🎊 Поздравляем победителей!"
                
                await message.answer(result)
                my_raffles["participants"] = []
                return
        
        # Настройка призов для моего розыгрыша
        if "1 место" in text and "2 место" in text:
            try:
                parts = text.split(",")
                for part in parts:
                    if "1 место" in part:
                        my_raffles["prizes"][0] = part.split(":")[1].strip()
                    elif "2 место" in part:
                        my_raffles["prizes"][1] = part.split(":")[1].strip()
                    elif "3 место" in part:
                        my_raffles["prizes"][2] = part.split(":")[1].strip()
                await message.answer("✅ Призы для моего розыгрыша сохранены!")
            except:
                await message.answer("❌ Неправильный формат!")
            return
    
    # Создание розыгрыша пользователем
    if " @" in message.text and "ДД.ММ.ГГГГ" not in message.text:
        try:
            parts = message.text.split(" ")
            channel = parts[0]
            date_str = parts[1] + " " + parts[2]
            prizes_text = " ".join(parts[3:])
            
            end_date = datetime.strptime(date_str, "%d.%m.%Y %H:%M").timestamp()
            prize_list = ["Главный приз", "Второй приз", "Третий приз"]
            if "1 место" in prizes_text:
                prize_list = []
                for part in prizes_text.split(","):
                    prize_list.append(part.split(":")[1].strip())
            
            raffle_counter += 1
            raffles[raffle_counter] = {
                "creator": message.from_user.id,
                "channel": channel,
                "end_date": end_date,
                "prizes": prize_list,
                "participants": [],
                "winner": None,
                "status": "active"
            }
            
            # Кнопка для участия в этом розыгрыше
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Участвовать", callback_data=f"join_raffle_{raffle_counter}")]
            ])
            
            await message.answer(
                f"✅ Розыгрыш создан!\n\n"
                f"📢 Канал: {channel}\n"
                f"⏳ До: {datetime.fromtimestamp(end_date).strftime('%d.%m.%Y %H:%M')}\n"
                f"🏆 Призы: {', '.join(prize_list)}\n\n"
                f"🔔 Подпишись на канал и нажми кнопку!",
                reply_markup=keyboard
            )
        except Exception as e:
            await message.answer(
                "❌ Неправильный формат!\n"
                "Пример: @my_channel 10.07.2026 15:00 1 место: iPhone, 2 место: AirPods"
            )

# ========== УЧАСТИЕ В ЧУЖОМ РОЗЫГРЫШЕ ==========
@dp.callback_query(F.data.startswith("join_raffle_"))
async def join_raffle(callback: types.CallbackQuery):
    raffle_id = int(callback.data.split("_")[2])
    raffle = raffles.get(raffle_id)
    
    if not raffle or raffle["status"] != "active":
        await callback.answer("❌ Розыгрыш уже завершён!", show_alert=True)
        return
    
    # Проверка подписки
    try:
        status = await bot.get_chat_member(raffle["channel"], callback.from_user.id)
        if status.status in ["left", "kicked"]:
            await callback.answer(f"❌ Подпишись на {raffle['channel']}!", show_alert=True)
            return
    except:
        await callback.answer("⚠️ Ошибка проверки подписки!", show_alert=True)
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
    
    await callback.answer("✅ Вы участвуете в розыгрыше!", show_alert=False)

# ========== АДМИН-ФУНКЦИИ (callback) ==========
@dp.callback_query(F.data == "my_list")
async def my_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    if len(my_raffles["participants"]) == 0:
        await callback.message.answer("📭 Моих участников нет.")
        await callback.answer()
        return
    
    text = "📋 Мои участники:\n\n"
    for i, p in enumerate(my_raffles["participants"], 1):
        text += f"{i}. @{p['username']} ({p['first_name']}) — ID: {p['user_id']}\n"
    
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "my_pick")
async def my_pick(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    if len(my_raffles["participants"]) == 0:
        await callback.message.answer("❌ Нет участников!")
        await callback.answer()
        return
    
    await callback.message.answer("🎲 Введите количество победителей (от 1 до 10):")
    await callback.answer()

@dp.callback_query(F.data == "my_clear")
async def my_clear(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    my_raffles["participants"] = []
    await callback.message.answer("✅ Мои участники очищены!")
    await callback.answer()

@dp.callback_query(F.data == "all_raffles")
async def all_raffles_admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    
    if not raffles:
        await callback.message.answer("📭 Нет розыгрышей.")
        await callback.answer()
        return
    
    text = "📊 ВСЕ РОЗЫГРЫШИ:\n\n"
    for idx, (rid, r) in enumerate(raffles.items(), 1):
        creator = await bot.get_chat(r["creator"])
        text += f"{idx}. Создатель: @{creator.username or 'неизвестно'}\n"
        text += f"   📢 Канал: {r['channel']}\n"
        text += f"   👥 Участников: {len(r['participants'])}\n"
        text += f"   ⏳ До: {datetime.fromtimestamp(r['end_date']).strftime('%d.%m.%Y %H:%M')}\n"
        text += f"   🏆 Призы: {', '.join(r['prizes'])}\n"
        text += f"   ❗️ Статус: {r['status']}\n\n"
    
    await callback.message.answer(text)
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    print("🤖 Randomazer запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
