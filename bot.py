import asyncio
import base64
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


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
