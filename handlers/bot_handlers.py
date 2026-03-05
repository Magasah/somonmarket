"""Somon Market — Telegram Bot Handlers.

Commands:
  /start        — приветствие + WebApp кнопка
  /help         — список команд
  /balance      — текущий баланс
  /orders       — последние заказы
  /support      — написать в поддержку
  /admin        — панель администратора (только ADMIN_IDS)
  /broadcast    — рассылка всем (только ADMIN_IDS)
  /ban <id>     — блокировка пользователя
  /unban <id>   — разблокировка
  /stats        — статистика платформы
"""

import os
import logging
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

logger = logging.getLogger(__name__)

router = Router()
DB_NAME = "somon_market.db"

WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8000")

# Telegram IDs администраторов через запятую в .env: ADMIN_IDS=123456,789012
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}


# ─── FSM ─────────────────────────────────────────────────────────────────────

class AddProduct(StatesGroup):
    name     = State()
    price    = State()
    category = State()

class BroadcastState(StatesGroup):
    message = State()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_kb() -> InlineKeyboardMarkup | None:
    if not WEB_APP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍  Открыть маркетплейс", web_app=WebAppInfo(url=f"{WEB_APP_URL}/web"))],
        [InlineKeyboardButton(text="📦 Заказы", callback_data="cb_orders"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="cb_balance")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="cb_support")],
    ])


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    name = message.from_user.first_name or "Друг"
    kb   = main_kb()
    body = (
        f"👋 Салом, <b>{name}</b>!\n\n"
        "Добро пожаловать в <b>Somon Game Market</b> — "
        "площадку для покупки и продажи игровых аккаунтов,\n"
        "внутриигровой валюты, скинов и подписок.\n\n"
        "🔒 Сделки через <b>Escrow</b>\n"
        "⭐ Рейтинг продавцов\n"
        "⚡ Мгновенная доставка\n\n"
    )
    body += "Нажми кнопку ниже 👇" if kb else (
        "⚠️ WebApp требует HTTPS.\n"
        f"WEB_APP_URL: <code>{WEB_APP_URL}</code>"
    )
    await message.answer(body, parse_mode="HTML", reply_markup=kb)


# ─── /help ────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "📋 <b>Команды</b>\n\n"
        "/start   — главное меню\n"
        "/balance — ваш баланс\n"
        "/orders  — заказы\n"
        "/support — поддержка\n",
        parse_mode="HTML",
    )


# ─── /balance ─────────────────────────────────────────────────────────────────

@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    tg_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE telegram_id=?", (tg_id,)) as c:
            row = await c.fetchone()
    if row:
        await message.answer(f"💰 Баланс: <code>{float(row[0]):.2f} TJS</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Аккаунт не найден. Откройте маркетплейс через /start")


# ─── /orders ──────────────────────────────────────────────────────────────────

@router.message(Command("orders"))
async def cmd_orders(message: types.Message) -> None:
    await message.answer(
        "📦 История заказов → <b>Маркетплейс → Профиль → Мои покупки</b>",
        parse_mode="HTML", reply_markup=main_kb(),
    )


# ─── /support ─────────────────────────────────────────────────────────────────

@router.message(Command("support"))
async def cmd_support(message: types.Message) -> None:
    await message.answer(
        "🆘 <b>Поддержка</b>\n\nОпишите проблему — ответим в течение 2 часов.",
        parse_mode="HTML",
    )


# ─── /stats (admin) ───────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав.")
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM items WHERE status='ACTIVE'") as c:
            active = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM items") as c:
            total_items = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders") as c:
            orders_total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status='COMPLETED'") as c:
            orders_done = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(price),0) FROM orders WHERE status='COMPLETED'") as c:
            revenue = (await c.fetchone())[0]
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <code>{users}</code>\n"
        f"🟢 Активных товаров: <code>{active}</code>\n"
        f"📦 Всего товаров: <code>{total_items}</code>\n\n"
        f"🛒 Заказов всего: <code>{orders_total}</code>\n"
        f"✅ Завершённых: <code>{orders_done}</code>\n"
        f"💰 Выручка: <code>{revenue:.2f} TJS</code>",
        parse_mode="HTML",
    )


# ─── /admin ───────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав администратора.")
        return
    rows = [
        [InlineKeyboardButton(text="📊 Статистика",  callback_data="adm_stats")],
        [InlineKeyboardButton(text="📣 Рассылка",    callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📦 Товары",      callback_data="adm_items")],
    ]
    if WEB_APP_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(
            text="🌐 Открыть Admin Panel",
            web_app=WebAppInfo(url=f"{WEB_APP_URL}/web"),
        )])
    await message.answer(
        "🛡 <b>Admin Panel</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ─── /broadcast ───────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав.")
        return
    await state.set_state(BroadcastState.message)
    await message.answer("📣 Введите текст рассылки (/cancel для отмены):")


@router.message(BroadcastState.message)
async def do_broadcast(message: types.Message, state: FSMContext) -> None:
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return
    text = message.text or ""
    sent = failed = 0
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT telegram_id FROM users WHERE is_active=1") as c:
            rows = await c.fetchall()
    for (tid,) in rows:
        try:
            await message.bot.send_message(tid, f"📢 <b>Somon Market</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await state.clear()
    await message.answer(f"✅ Отправлено: {sent} | Ошибок: {failed}")


# ─── /ban  /unban ─────────────────────────────────────────────────────────────

@router.message(Command("ban"))
async def cmd_ban(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав."); return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /ban <telegram_id>"); return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_active=0 WHERE telegram_id=?", (int(parts[1]),))
        await db.commit()
    await message.answer(f"🚫 <code>{parts[1]}</code> заблокирован.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав."); return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /unban <telegram_id>"); return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_active=1 WHERE telegram_id=?", (int(parts[1]),))
        await db.commit()
    await message.answer(f"✅ <code>{parts[1]}</code> разблокирован.", parse_mode="HTML")


# ─── Callbacks ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cb_balance")
async def _cb_balance(call: types.CallbackQuery) -> None:
    await call.answer(); await cmd_balance(call.message)

@router.callback_query(F.data == "cb_orders")
async def _cb_orders(call: types.CallbackQuery) -> None:
    await call.answer(); await cmd_orders(call.message)

@router.callback_query(F.data == "cb_support")
async def _cb_support(call: types.CallbackQuery) -> None:
    await call.answer(); await cmd_support(call.message)

@router.callback_query(F.data == "adm_stats")
async def _cb_stats(call: types.CallbackQuery) -> None:
    await call.answer()
    if is_admin(call.from_user.id): await cmd_stats(call.message)

@router.callback_query(F.data == "adm_broadcast")
async def _cb_bcast(call: types.CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    if is_admin(call.from_user.id):
        await state.set_state(BroadcastState.message)
        await call.message.answer("📣 Введите текст рассылки:")

@router.callback_query(F.data == "adm_items")
async def _cb_items(call: types.CallbackQuery) -> None:
    await call.answer()
    if not is_admin(call.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id,title,price,status FROM items ORDER BY id DESC LIMIT 10"
        ) as c:
            rows = await c.fetchall()
    if not rows:
        await call.message.answer("Товаров нет."); return
    lines = "\n".join(f"#{r[0]} | {r[1][:28]} | {r[2]} TJS | {r[3]}" for r in rows)
    await call.message.answer(f"<pre>{lines}</pre>", parse_mode="HTML")


# Ссылка на твой сайт (из ngrok)
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8000") 

# --- МАШИНА СОСТОЯНИЙ (Чтобы бот запоминал ответы) ---
class AddProduct(StatesGroup):
    name = State()
    price = State()
    category = State()

# --- КОМАНДА /START ---
@router.message(CommandStart())
async def cmd_start(message: types.Message):
   # В функции cmd_start добавь вторую кнопку:
    # Добавляем Web App кнопки только если URL безопасный (https://)
    if WEB_APP_URL.startswith("https://"):
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛍 Купить", web_app=WebAppInfo(url=f"{WEB_APP_URL}/"))],
            [types.InlineKeyboardButton(text="➕ Продать (Face ID)", web_app=WebAppInfo(url=f"{WEB_APP_URL}/sell"))]
        ])
        await message.answer(
            "Салом! Добро пожаловать в Somon Game Market.\nЖми кнопку снизу 👇",
            reply_markup=kb
        )
    else:
        # Безопасный Web App URL не настроен — предупреждаем администратора
        await message.answer(
            "Салом! Для запуска Web App кнопок нужен HTTPS URL.\n"
            "Установите переменную окружения WEB_APP_URL на публичный HTTPS-адрес (например, ngrok с --https)\n"
            f"Текущий WEB_APP_URL: {WEB_APP_URL}\n\n"
            "Пока что используйте бота без Web App кнопок.")

# --- АДМИНКА: ДОБАВИТЬ ТОВАР ---
# Пишешь /add - бот спрашивает название
@router.message(Command("add"))
async def start_add_product(message: types.Message, state: FSMContext):
    # Тут можно добавить проверку на ID админа (if message.from_user.id == ТВОЙ_ID)
    await state.set_state(AddProduct.name)
    await message.answer("Введите название товара (например: 100 Алмазов):")

@router.message(AddProduct.name)
async def add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("Введите цену (только цифры, например: 15):")

@router.message(AddProduct.price)
async def add_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(AddProduct.category)
    await message.answer("Введите категорию (Free Fire, PUBG, CS):")

@router.message(AddProduct.category)
async def add_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data['name']
    price = data['price']
    category = message.text

    # Сохраняем в Базу Данных
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO products (game_type, category, name, price) VALUES (?, ?, ?, ?)",
            (category, category, name, price)
        )
        await db.commit()

    await message.answer(f"✅ Товар добавлен!\n{name} - {price} TJS")
    await state.clear()