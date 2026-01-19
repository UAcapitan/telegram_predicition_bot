import asyncio
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
import psycopg

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "affiliate_link": "https://example.com",
    "contact_link": "https://t.me/mixeed22",
}


@dataclass
class AppConfig:
    token: str
    admin_ids: set[int]


def load_app_config() -> AppConfig:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    admin_raw = os.getenv("ADMIN_IDS", "").strip()

    if not token:
        raise RuntimeError("BOT_TOKEN is missing in environment")

    admin_ids: set[int] = set()
    if admin_raw:
        for part in admin_raw.split(","):
            part = part.strip()
            if part:
                admin_ids.add(int(part))

    return AppConfig(token=token, admin_ids=admin_ids)

def get_database_url() -> str:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing in environment")
    return db_url


def _load_legacy_subscribers() -> list[int]:
    if not SUBSCRIBERS_FILE.exists():
        return []
    try:
        data = json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    legacy_ids: list[int] = []
    for value in data:
        try:
            legacy_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return legacy_ids


def _load_legacy_config() -> dict:
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_CONFIG.copy()
    if not isinstance(data, dict):
        return DEFAULT_CONFIG.copy()
    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in data.items() if isinstance(k, str)})
    return merged


def ensure_database() -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id BIGINT PRIMARY KEY
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            legacy_ids = _load_legacy_subscribers()
            if legacy_ids:
                cur.execute("SELECT COUNT(*) FROM subscribers")
                count = cur.fetchone()[0]
                if count == 0:
                    cur.executemany(
                        "INSERT INTO subscribers (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                        [(user_id,) for user_id in legacy_ids],
                    )
            cur.execute("SELECT COUNT(*) FROM bot_config")
            config_count = cur.fetchone()[0]
            if config_count == 0:
                legacy_config = _load_legacy_config()
                cur.executemany(
                    "INSERT INTO bot_config (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(key, str(value)) for key, value in legacy_config.items()],
                )


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    if not SUBSCRIBERS_FILE.exists():
        SUBSCRIBERS_FILE.write_text("[]", encoding="utf-8")

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    ensure_database()

def load_subscribers() -> set[int]:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM subscribers")
            return {row[0] for row in cur.fetchall()}


def add_subscriber(user_id: int) -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subscribers (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (user_id,),
            )


def load_bot_config() -> dict:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM bot_config")
            rows = cur.fetchall()
            if not rows:
                return DEFAULT_CONFIG.copy()
            config = DEFAULT_CONFIG.copy()
            config.update({key: value for key, value in rows})
            return config


def save_bot_config(config: dict) -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO bot_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                [(key, str(value)) for key, value in config.items()],
            )


def build_links_keyboard(config: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    affiliate = config.get("affiliate_link", "")
    contact = config.get("contact_link", "")

    if affiliate:
        builder.button(text="Get Prediction", url=affiliate)
    if contact:
        builder.button(text="Contact", url=contact)

    return builder.as_markup()


def get_random_image() -> Path:
    images = [
        p
        for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
    ]
    if not images:
        raise FileNotFoundError("No images found in data/images")
    return random.choice(images)


def is_admin(message: Message, config: AppConfig) -> bool:
    return message.from_user and message.from_user.id in config.admin_ids


async def cmd_start(message: Message, config: AppConfig) -> None:
    if message.from_user:
        add_subscriber(message.from_user.id)

    await message.answer(
        "Welcome! Tap /predict to get a random prediction image."
    )


async def cmd_predict(message: Message) -> None:
    try:
        image_path = get_random_image()
    except FileNotFoundError:
        await message.answer("No prediction images yet. Add files to data/images.")
        return

    config = load_bot_config()
    keyboard = build_links_keyboard(config)

    await message.answer_photo(
        photo=FSInputFile(str(image_path)),
        caption="Your prediction is ready!",
        reply_markup=keyboard,
    )


async def cmd_broadcast(message: Message, command: CommandObject, config: AppConfig) -> None:
    if not is_admin(message, config):
        await message.answer("Admin only.")
        return

    text = command.args
    if not text:
        await message.answer("Usage: /broadcast your message")
        return

    subscribers = load_subscribers()
    if not subscribers:
        await message.answer("No subscribers yet.")
        return

    sent = 0
    failed = 0
    for user_id in subscribers:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1

    result_text = f"Broadcast complete. Sent: {sent}, Failed: {failed}."
    await message.answer(result_text)
    for admin_id in config.admin_ids:
        if message.from_user and admin_id == message.from_user.id:
            continue
        try:
            await message.bot.send_message(admin_id, result_text)
        except Exception:
            continue


async def cmd_setlink(message: Message, command: CommandObject, config: AppConfig) -> None:
    if not is_admin(message, config):
        await message.answer("Admin only.")
        return

    new_link = (command.args or "").strip()
    if not new_link:
        await message.answer("Usage: /setlink https://your-link")
        return

    current = load_bot_config()
    current["affiliate_link"] = new_link
    save_bot_config(current)

    await message.answer("Affiliate link updated.")


async def cmd_setcontact(message: Message, command: CommandObject, config: AppConfig) -> None:
    if not is_admin(message, config):
        await message.answer("Admin only.")
        return

    new_link = (command.args or "").strip()
    if not new_link:
        await message.answer("Usage: /setcontact https://t.me/your_contact")
        return

    current = load_bot_config()
    current["contact_link"] = new_link
    save_bot_config(current)

    await message.answer("Contact link updated.")


async def main() -> None:
    ensure_storage()
    app_config = load_app_config()

    bot = Bot(token=app_config.token)
    dp = Dispatcher()

    async def cmd_start_entry(message: Message) -> None:
        await cmd_start(message, app_config)

    async def cmd_broadcast_entry(message: Message, command: CommandObject) -> None:
        await cmd_broadcast(message, command, app_config)

    async def cmd_setlink_entry(message: Message, command: CommandObject) -> None:
        await cmd_setlink(message, command, app_config)

    async def cmd_setcontact_entry(message: Message, command: CommandObject) -> None:
        await cmd_setcontact(message, command, app_config)

    dp.message.register(cmd_start_entry, Command("start"))
    dp.message.register(cmd_predict, Command("predict"))
    dp.message.register(
        cmd_broadcast_entry,
        Command("broadcast"),
    )
    dp.message.register(
        cmd_setlink_entry,
        Command("setlink"),
    )
    dp.message.register(
        cmd_setcontact_entry,
        Command("setcontact"),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
