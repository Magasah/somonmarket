import asyncio
import base64
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN: str        = os.getenv("BOT_TOKEN", "")
ADMIN_ID_RAW: str     = os.getenv("ADMIN_ID", "")
ADMIN_IDS_RAW: str    = os.getenv("ADMIN_IDS", "")
WEBAPP_URL: str       = os.getenv("WEBAPP_URL", "https://google.com").strip()
ADMIN_SECRET: str     = os.getenv("ADMIN_SECRET", "")
CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "").strip().lstrip("@")
CHANNEL_ID_RAW: str   = os.getenv("CHANNEL_ID", "").strip()

if not WEBAPP_URL.startswith(("https://", "http://")):
    WEBAPP_URL = "https://google.com"

CHANNEL_ID: Optional[int] = None
if CHANNEL_ID_RAW.lstrip("-").isdigit():
    CHANNEL_ID = int(CHANNEL_ID_RAW)

ADMIN_IDS: list[int] = []
for _v in ADMIN_IDS_RAW.split(","):
    _v = _v.strip()
    if _v.isdigit():
        ADMIN_IDS.append(int(_v))
if not ADMIN_IDS and ADMIN_ID_RAW.isdigit():
    ADMIN_IDS.append(int(ADMIN_ID_RAW))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FSM ───────────────────────────────────────────────────────────────────────
class UserState(StatesGroup):
    choosing_lang    = State()
    checking_sub     = State()

# ── i18n strings ─────────────────────────────────────────────────────────────
TEXTS = {
    "ru": {
        "choose_lang":      "🌐 Выберите язык / Забонро интихоб кунед:",
        "welcome":          (
            "👋 Привет, {name}!\n\n"
            "🎮 Добро пожаловать в *Somon Market* — крупнейший маркетплейс "
            "игровых аккаунтов в Таджикистане!\n\n"
            "🔸 Покупай и продавай аккаунты CS2, Fortnite, Roblox и других игр\n"
            "🔸 Безопасные сделки с защитой покупателя\n"
            "🔸 Быстрая поддержка 24/7\n\n"
            "Нажми кнопку ниже чтобы войти 👇"
        ),
        "open_market":      "🛒 Открыть Маркетплейс",
        "sub_required":     (
            "⚠️ Для использования бота необходимо подписаться на наш канал!\n\n"
            "📢 Подпишитесь и нажмите *«Я подписался»*"
        ),
        "sub_channel_btn":  "📢 Подписаться на канал",
        "sub_check_btn":    "✅ Я подписался",
        "sub_ok":           "✅ Подписка подтверждена! Добро пожаловать!",
        "sub_fail":         "❌ Вы ещё не подписались на канал. Пожалуйста, подпишитесь и попробуйте снова.",
        "help":             (
            "📋 *Команды Somon Market:*\n\n"
            "/start — Открыть маркетплейс\n"
            "/lang — Сменить язык\n"
            "/help — Список команд\n"
            "/support — Поддержка\n"
            "/admin — Панель администратора\n\n"
            "По вопросам: @somon_support"
        ),
        "support":          (
            "🆘 *Поддержка Somon Market*\n\n"
            "Если есть проблема с заказом — опишите ситуацию.\n"
            "Ответим в течение 24 часов.\n\n"
            "Или используйте встроенный чат в маркетплейсе:"
        ),
        "admin_forbidden":  "⛔ Доступ запрещён.",
        "admin_no_secret":  "⚠️ ADMIN_SECRET не задан. Установите его в .env.",
        "admin_panel":      "🛡 *Admin Panel*\nНажми кнопку для входа в панель:",
        "admin_btn":        "🛡 Открыть Admin Panel",
        "lang_changed":     "✅ Язык изменён на Русский",
        "cmd_start":        "🎮 Открыть Somon Market",
        "cmd_help":         "📋 Список команд",
        "cmd_support":      "🆘 Поддержка",
        "cmd_lang":         "🌐 Сменить язык",
        "cmd_admin":        "🛡 Панель администратора",
    },
    "tj": {
        "choose_lang":      "🌐 Забонро интихоб кунед / Выберите язык:",
        "welcome":          (
            "👋 Салом, {name}!\n\n"
            "🎮 Хуш омадед ба *Somon Market* — калонтарин маркетплейси "
            "бозиҳо дар Тоҷикистон!\n\n"
            "🔸 Аккаунтҳои CS2, Fortnite, Roblox ва дигар бозиҳоро харед ва фурӯшед\n"
            "🔸 Муомилаҳои бехатар бо ҳимояти харидор\n"
            "🔸 Дастгирии зуд 24/7\n\n"
            "Тугмаи зеринро пахш кунед 👇"
        ),
        "open_market":      "🛒 Кушодани Маркетплейс",
        "sub_required":     (
            "⚠️ Барои истифодаи бот бояд ба канали мо обуна шавед!\n\n"
            "📢 Обуна шавед ва *«Обуна шудам»* -ро пахш кунед"
        ),
        "sub_channel_btn":  "📢 Обуна шудан ба канал",
        "sub_check_btn":    "✅ Обуна шудам",
        "sub_ok":           "✅ Обуна тасдиқ шуд! Хуш омадед!",
        "sub_fail":         "❌ Шумо ҳанӯз ба канал обуна нашудаед. Лутфан обуна шавед ва дубора кӯшиш кунед.",
        "help":             (
            "📋 *Амрҳои Somon Market:*\n\n"
            "/start — Кушодани маркетплейс\n"
            "/lang — Иваз кардани забон\n"
            "/help — Рӯйхати амрҳо\n"
            "/support — Дастгирӣ\n"
            "/admin — Панели маъмур\n\n"
            "Саволҳо: @somon_support"
        ),
        "support":          (
            "🆘 *Дастгирии Somon Market*\n\n"
            "Агар бо фармоиш мушкилот дошта бошед — вазъиятро тавсиф кунед.\n"
            "Дар муддати 24 соат ҷавоб медиҳем.\n\n"
            "Ё чати дохилиро дар маркетплейс истифода баред:"
        ),
        "admin_forbidden":  "⛔ Дастрасӣ рад шуд.",
        "admin_no_secret":  "⚠️ ADMIN_SECRET муайян нашудааст.",
        "admin_panel":      "🛡 *Панели Маъмур*\nТугмаро барои вуруд пахш кунед:",
        "admin_btn":        "🛡 Кушодани Панели Маъмур",
        "lang_changed":     "✅ Забон ба Тоҷикӣ тағйир ёфт",
        "cmd_start":        "🎮 Кушодани Somon Market",
        "cmd_help":         "📋 Рӯйхати амрҳо",
        "cmd_support":      "🆘 Дастгирӣ",
        "cmd_lang":         "🌐 Иваз кардани забон",
        "cmd_admin":        "🛡 Панели маъмур",
    },
}

# ── In-memory language store {user_id: "ru"/"tj"} ────────────────────────────
_user_lang: dict[int, str] = {}

def get_lang(user_id: int) -> str:
    return _user_lang.get(user_id, "tj")

def t(user_id: int, key: str) -> str:
    return TEXTS[get_lang(user_id)][key]

# ── Keyboards ─────────────────────────────────────────────────────────────────
def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="lang:ru"),
        InlineKeyboardButton(text="🇹🇯 Тоҷикӣ", callback_data="lang:tj"),
    ]])

def kb_webapp(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t(user_id, "open_market"),
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]])

def kb_sub(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if CHANNEL_USERNAME:
        rows.append([InlineKeyboardButton(
            text=t(user_id, "sub_channel_btn"),
            url=f"https://t.me/{CHANNEL_USERNAME}",
        )])
    rows.append([InlineKeyboardButton(
        text=t(user_id, "sub_check_btn"),
        callback_data="check_sub",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Subscription check ────────────────────────────────────────────────────────
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    if not CHANNEL_ID:
        return True  # проверка отключена если CHANNEL_ID не задан
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception as exc:
        logger.warning("Subscription check failed: %s", exc)
        return True  # при ошибке пропускаем (не блокируем пользователя)

# ── Helpers ───────────────────────────────────────────────────────────────────
async def send_welcome(message: Message) -> None:
    uid = message.from_user.id
    name = message.from_user.first_name or "друг"
    await message.answer(
        t(uid, "welcome").format(name=name),
        reply_markup=kb_webapp(uid),
        parse_mode="Markdown",
    )

# ── Router ────────────────────────────────────────────────────────────────────
router = Router(name="somon_market_router")
dp = Dispatcher(storage=MemoryStorage())

_bot: Optional[Bot] = None

# /start -----------------------------------------------------------------------
@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    # Шаг 1: выбор языка (если ещё не выбран)
    if uid not in _user_lang:
        await state.set_state(UserState.choosing_lang)
        await message.answer(
            TEXTS["tj"]["choose_lang"],
            reply_markup=kb_lang(),
        )
        return
    # Шаг 2: проверка подписки
    if not await is_subscribed(message.bot, uid):
        await state.set_state(UserState.checking_sub)
        await message.answer(
            t(uid, "sub_required"),
            reply_markup=kb_sub(uid),
            parse_mode="Markdown",
        )
        return
    # Шаг 3: приветствие
    await send_welcome(message)

# Callback: выбор языка --------------------------------------------------------
@router.callback_query(F.data.startswith("lang:"))
async def lang_callback(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    lang = call.data.split(":")[1]
    _user_lang[uid] = lang
    await call.message.edit_reply_markup(reply_markup=None)

    # После выбора языка — проверяем подписку
    if not await is_subscribed(call.bot, uid):
        await state.set_state(UserState.checking_sub)
        await call.message.answer(
            t(uid, "sub_required"),
            reply_markup=kb_sub(uid),
            parse_mode="Markdown",
        )
        await call.answer()
        return

    await state.clear()
    await send_welcome(call.message)
    await call.answer()

# Callback: проверка подписки --------------------------------------------------
@router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    if await is_subscribed(call.bot, uid):
        await state.clear()
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer(t(uid, "sub_ok"), show_alert=True)
        await send_welcome(call.message)
    else:
        await call.answer(t(uid, "sub_fail"), show_alert=True)

# /lang ------------------------------------------------------------------------
@router.message(Command("lang"))
async def lang_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(UserState.choosing_lang)
    await message.answer(TEXTS["tj"]["choose_lang"], reply_markup=kb_lang())

# /help ------------------------------------------------------------------------
@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    uid = message.from_user.id
    await message.answer(t(uid, "help"), parse_mode="Markdown")

# /support ---------------------------------------------------------------------
@router.message(Command("support"))
async def support_handler(message: Message) -> None:
    uid = message.from_user.id
    await message.answer(
        t(uid, "support"),
        reply_markup=kb_webapp(uid),
        parse_mode="Markdown",
    )

# /admin -----------------------------------------------------------------------
@router.message(Command("admin"))
async def admin_handler(message: Message) -> None:
    uid = message.from_user.id
    if not ADMIN_IDS or uid not in ADMIN_IDS:
        await message.answer(t(uid, "admin_forbidden"))
        return
    if not ADMIN_SECRET:
        await message.answer(t(uid, "admin_no_secret"))
        return
    admin_url = f"{WEBAPP_URL}/web?at={ADMIN_SECRET}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid, "admin_btn"), web_app=WebAppInfo(url=admin_url))
    ]])
    await message.answer(t(uid, "admin_panel"), reply_markup=kb, parse_mode="Markdown")

# ── notify_admin (used by main.py FastAPI) ────────────────────────────────────
def _decode_base64_payload(photo_base64: str) -> bytes:
    raw = photo_base64.split(",", 1)[1] if "," in photo_base64 else photo_base64
    return base64.b64decode(raw, validate=True)

async def notify_admin(text: str, photo_base64: str = None) -> None:
    try:
        if _bot is None:
            logger.warning("notify_admin skipped: bot not initialized")
            return
        if not ADMIN_IDS:
            logger.warning("notify_admin skipped: no ADMIN_IDS")
            return
        if photo_base64:
            photo_bytes = _decode_base64_payload(photo_base64)
            for aid in ADMIN_IDS:
                await _bot.send_photo(chat_id=aid, photo=BufferedInputFile(photo_bytes, "notification.jpg"), caption=text)
            return
        for aid in ADMIN_IDS:
            await _bot.send_message(chat_id=aid, text=text)
    except Exception as exc:
        logger.exception("notify_admin error: %s", exc)


async def notify_user(tg_id: int, text: str) -> None:
    """Send a notification message to a specific user by their Telegram ID."""
    if _bot is None:
        logger.warning("notify_user skipped: bot not initialized")
        return
    try:
        await _bot.send_message(chat_id=tg_id, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.warning("notify_user failed for tg_id=%s: %s", tg_id, exc)


# /ref -------------------------------------------------------------------------
@router.message(Command("ref"))
async def ref_handler(message: Message) -> None:
    uid = message.from_user.id
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username or ""
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    if get_lang(uid) == "tj":
        text = (
            f"🎁 *Дӯсти худро даъват кунед!*\n\n"
            f"Ҳар нафаре ки тавассути истиноди шумо сабт мешавад:\n"
            f"• Дӯсти шумо +10 TJS мегирад\n"
            f"• Шумо +20 TJS мегиред\n\n"
            f"🔗 Истиноди шумо:\n`{ref_link}`"
        )
    else:
        text = (
            f"🎁 *Пригласите друга!*\n\n"
            f"За каждого приглашённого пользователя:\n"
            f"• Ваш друг получает +10 TJS\n"
            f"• Вы получаете +20 TJS\n\n"
            f"🔗 Ваша реферальная ссылка:\n`{ref_link}`"
        )
    await message.answer(text, parse_mode="Markdown")

# ── Entry point ───────────────────────────────────────────────────────────────
async def main() -> None:
    global _bot

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN in .env")

    _bot = Bot(token=BOT_TOKEN)

    from aiogram.types import BotCommand, BotCommandScopeDefault
    # Команды показываются на языке Тоджикском по умолчанию
    await _bot.set_my_commands([
        BotCommand(command="start",   description="🎮 Кушодани Somon Market"),
        BotCommand(command="lang",    description="🌐 Иваз кардани забон / Сменить язык"),
        BotCommand(command="ref",     description="🎁 Реферальная ссылка / Истиноди реферал"),
        BotCommand(command="help",    description="📋 Рӯйхати амрҳо"),
        BotCommand(command="support", description="🆘 Дастгирӣ"),
        BotCommand(command="admin",   description="🛡 Панели маъмур"),
    ], scope=BotCommandScopeDefault())

    dp.include_router(router)
    logger.info("Bot started. WEBAPP_URL=%s | CHANNEL_ID=%s", WEBAPP_URL, CHANNEL_ID)
    await dp.start_polling(_bot)


if __name__ == "__main__":
    asyncio.run(main())



BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID_RAW: str = os.getenv("ADMIN_ID", "")
ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS", "")
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "https://google.com").strip()
if not WEBAPP_URL.startswith(("https://", "http://")):
    WEBAPP_URL = "https://google.com"

ADMIN_SECRET: str = os.getenv("ADMIN_SECRET", "")

ADMIN_IDS: list[int] = []
for raw_value in ADMIN_IDS_RAW.split(","):
    value = raw_value.strip()
    if value.isdigit():
        ADMIN_IDS.append(int(value))

if not ADMIN_IDS and ADMIN_ID_RAW.isdigit():
    ADMIN_IDS.append(int(ADMIN_ID_RAW))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router(name="somon_market_router")
dp = Dispatcher()

_bot: Optional[Bot] = None


def build_webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Кушодани Маркетплейс",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )


@router.message(Command("admin"))
async def admin_handler(message: Message) -> None:
    if not ADMIN_IDS or message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    if not ADMIN_SECRET:
        await message.answer("⚠️ ADMIN_SECRET не задан. Установите его в .env.")
        return
    admin_url = f"{WEBAPP_URL}/web?at={ADMIN_SECRET}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🛡 Открыть Admin Panel",
                web_app=WebAppInfo(url=admin_url),
            )
        ]]
    )
    await message.answer("🛡 *Admin Panel*\nНажми кнопку для входа в панель:", reply_markup=kb, parse_mode="Markdown")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Салом, {name}!\n\n🎮 Хуш омадед ба *Somon Market* — калонтарин маркетплейси бозиҳо дар Тоҷикистон!\n\nБарои оғоз тугмаи поёнро пахш кунед 👇",
        reply_markup=build_webapp_keyboard(),
        parse_mode="Markdown",
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "📋 *Команды Somon Market:*\n\n"
        "/start — Открыть маркетплейс\n"
        "/help — Список команд\n"
        "/admin — Панель администратора (только для админов)\n\n"
        "По вопросам: @somon_support",
        parse_mode="Markdown",
    )


@router.message(Command("support"))
async def support_handler(message: Message) -> None:
    await message.answer(
        "🆘 *Поддержка Somon Market*\n\n"
        "Если у вас проблема с заказом или аккаунтом — опишите ситуацию ниже.\n"
        "Мы ответим в течение 24 часов.\n\n"
        "Или откройте маркетплейс и используйте встроенный чат:",
        reply_markup=build_webapp_keyboard(),
        parse_mode="Markdown",
    )


def _decode_base64_payload(photo_base64: str) -> bytes:
    raw_data = photo_base64.split(",", 1)[1] if "," in photo_base64 else photo_base64
    return base64.b64decode(raw_data, validate=True)


async def notify_admin(text: str, photo_base64: str = None) -> None:
    try:
        if _bot is None:
            logger.warning("notify_admin skipped: bot is not initialized")
            return
        if not ADMIN_IDS:
            logger.warning("notify_admin skipped: ADMIN_ID/ADMIN_IDS is missing or invalid")
            return

        if photo_base64:
            photo_bytes = _decode_base64_payload(photo_base64)
            for admin_id in ADMIN_IDS:
                photo = BufferedInputFile(photo_bytes, filename="notification.jpg")
                await _bot.send_photo(chat_id=admin_id, photo=photo, caption=text)
            return

        for admin_id in ADMIN_IDS:
            await _bot.send_message(chat_id=admin_id, text=text)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to notify admin: %s", exc)


async def main() -> None:
    global _bot

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN in .env or environment variables.")

    _bot = Bot(token=BOT_TOKEN)

    # Устанавливаем команды в меню бота
    from aiogram.types import BotCommand
    await _bot.set_my_commands([
        BotCommand(command="start",   description="🎮 Открыть Somon Market"),
        BotCommand(command="help",    description="📋 Список команд"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="admin",   description="🛡 Панель администратора"),
    ])

    dp.include_router(router)
    logger.info("Bot started. WEBAPP_URL=%s", WEBAPP_URL)
    await dp.start_polling(_bot)


if __name__ == "__main__":
    asyncio.run(main())
