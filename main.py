import asyncio
import json
import os
import random
from typing import Union
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
import psycopg

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
CONFIG_FILE = DATA_DIR / "config.json"
TRANSLATIONS_FILE = DATA_DIR / "translations.json"

DEFAULT_CONFIG = {
    "affiliate_link": "https://example.com",
    "contact_link": "https://t.me/mixeed22",
    "notify_new_subscribers": "false",
}

LANGUAGES = {
    "it": "Italiano",
    "pl": "Polski",
    "sr": "Srpski",
    "fr": "Français",
    "es": "Español",
    "de": "Deutsch",
    "en": "English",
}

LANGUAGE_FLAGS = {
    "en": "🇺🇸",
    "pl": "🇵🇱",
    "sr": "🇷🇸",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "de": "🇩🇪",
    "it": "🇮🇹",
}

DEFAULT_LANGUAGE = "en"


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
                f"""
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id BIGINT PRIMARY KEY,
                    lng TEXT NOT NULL DEFAULT '{DEFAULT_LANGUAGE}',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    unsubscribed_at TIMESTAMPTZ
                )
                """,
            )
            cur.execute(
                f"""
                ALTER TABLE subscribers
                ADD COLUMN IF NOT EXISTS lng TEXT NOT NULL DEFAULT '{DEFAULT_LANGUAGE}'
                """,
            )
            cur.execute(
                """
                ALTER TABLE subscribers
                ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE
                """,
            )
            cur.execute(
                """
                ALTER TABLE subscribers
                ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ
                """,
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
    if not TRANSLATIONS_FILE.exists():
        TRANSLATIONS_FILE.write_text("{}", encoding="utf-8")
    ensure_database()

def load_subscribers() -> set[int]:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM subscribers WHERE active = TRUE")
            return {row[0] for row in cur.fetchall()}


def get_user_language(user_id: int) -> str:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT lng FROM subscribers WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    return DEFAULT_LANGUAGE


def user_exists(user_id: int) -> bool:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM subscribers WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None


def is_user_active(user_id: int) -> bool:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT active FROM subscribers WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return bool(row[0]) if row else False


def get_or_create_user_language(user_id: int) -> str:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT lng, active FROM subscribers WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                if not row[1]:
                    cur.execute(
                        """
                        UPDATE subscribers
                        SET active = TRUE, unsubscribed_at = NULL
                        WHERE user_id = %s
                        """,
                        (user_id,),
                    )
                return row[0]
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lng, active, unsubscribed_at)
                VALUES (%s, %s, TRUE, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET active = TRUE, unsubscribed_at = NULL
                """,
                (user_id, DEFAULT_LANGUAGE),
            )
            return DEFAULT_LANGUAGE


def set_user_status(user_id: int, active: bool) -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            if active:
                cur.execute(
                    """
                    UPDATE subscribers
                    SET active = TRUE, unsubscribed_at = NULL
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
            else:
                cur.execute(
                    """
                    UPDATE subscribers
                    SET active = FALSE, unsubscribed_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )


def upsert_user_language(user_id: int, language: str) -> bool:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lng, active, unsubscribed_at)
                VALUES (%s, %s, TRUE, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    lng = EXCLUDED.lng,
                    active = TRUE,
                    unsubscribed_at = NULL
                RETURNING (xmax = 0) AS inserted
                """,
                (user_id, language),
            )
            row = cur.fetchone()
            return bool(row[0]) if row else False


def set_user_language(user_id: int, language: str) -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lng, active, unsubscribed_at)
                VALUES (%s, %s, TRUE, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    lng = EXCLUDED.lng,
                    active = TRUE,
                    unsubscribed_at = NULL
                """,
                (user_id, language),
            )


def load_translations() -> dict:
    if not TRANSLATIONS_FILE.exists():
        return {}
    try:
        data = json.loads(TRANSLATIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


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


def t(translations: dict, language: str, key: str) -> str:
    bucket = translations.get(language) or translations.get(DEFAULT_LANGUAGE, {})
    fallback = translations.get(DEFAULT_LANGUAGE, {})
    return bucket.get(key) or fallback.get(key, key)


def build_links_keyboard(config: dict, translations: dict, language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    affiliate = config.get("affiliate_link", "")
    contact = config.get("contact_link", "")

    next_button = InlineKeyboardButton(
        text=t(translations, language, "button_next"),
        callback_data="next_prediction",
    )
    builder.row(next_button)

    row_buttons = []
    if affiliate:
        row_buttons.append(
            InlineKeyboardButton(
                text=t(translations, language, "button_start"),
                url=affiliate,
            )
        )
    if contact:
        row_buttons.append(
            InlineKeyboardButton(
                text=t(translations, language, "button_support"),
                url=contact,
            )
        )
    if row_buttons:
        builder.row(*row_buttons)

    return builder.as_markup()

def build_main_keyboard(
    translations: dict,
    language: str,
    config: dict,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    get_prediction = InlineKeyboardButton(
        text=t(translations, language, "button_get_prediction"),
        callback_data="get_prediction",
    )
    change_language = InlineKeyboardButton(
        text=t(translations, language, "button_change_language"),
        callback_data="change_language",
    )
    start_button = InlineKeyboardButton(
        text=t(translations, language, "button_start_cmd"),
        callback_data="show_start",
    )
    builder.row(get_prediction, change_language)
    builder.row(start_button)
    contact = config.get("contact_link", "")
    if contact:
        builder.row(
            InlineKeyboardButton(
                text=t(translations, language, "button_support"),
                url=contact,
            )
        )
    return builder.as_markup()

def build_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, name in LANGUAGES.items():
        flag = LANGUAGE_FLAGS.get(code, "")
        label = f"{flag} {name}".strip() if flag else name
        builder.button(text=label, callback_data=f"set_lang:{code}")
    builder.adjust(2)
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


def build_prediction_caption(image_path: Path, translations: dict, language: str) -> str:
    stem = image_path.stem
    parts = stem.split("_")
    if len(parts) < 3:
        return t(translations, language, "prediction_default")

    difficulty_raw, first_num, after_dot = parts[0], parts[1], parts[2]
    if not (first_num.isdigit() and after_dot.isdigit()):
        return t(translations, language, "prediction_default")

    difficulty = difficulty_raw.replace("-", " ").replace("_", " ").title()
    value = f"{int(first_num)}.{after_dot}"
    return t(translations, language, "prediction_format").format(
        difficulty=difficulty,
        value=value,
    )


def is_admin(message: Message, config: AppConfig) -> bool:
    return message.from_user and message.from_user.id in config.admin_ids


def is_admin_user(user_id: int, config: AppConfig) -> bool:
    return user_id in config.admin_ids


def build_start_message(translations: dict, language: str) -> str:
    return t(translations, language, "start_user")


def build_admin_keyboard(translations: dict, language: str, notify_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t(translations, language, "admin_refresh"),
            callback_data="admin:refresh",
        )
    )
    notify_label = (
        t(translations, language, "admin_notify_on")
        if notify_enabled
        else t(translations, language, "admin_notify_off")
    )
    builder.row(
        InlineKeyboardButton(
            text=notify_label,
            callback_data="admin:toggle_notify",
        )
    )
    return builder.as_markup()


def get_bool_config(config: dict, key: str, default: bool = False) -> bool:
    raw = str(config.get(key, str(default))).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def format_language_label(code: str) -> str:
    name = LANGUAGES.get(code, code)
    flag = LANGUAGE_FLAGS.get(code, "")
    label = f"{flag} {name}".strip()
    return label


def get_subscriber_stats() -> tuple[int, int, dict[str, int]]:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subscribers WHERE active = TRUE")
            active_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM subscribers WHERE active = FALSE")
            inactive_count = cur.fetchone()[0]
            cur.execute(
                """
                SELECT lng, COUNT(*)
                FROM subscribers
                WHERE active = TRUE
                GROUP BY lng
                ORDER BY COUNT(*) DESC
                """
            )
            language_rows = cur.fetchall()
    per_language: dict[str, int] = {}
    for code, count in language_rows:
        if not code:
            code = DEFAULT_LANGUAGE
        per_language[str(code)] = int(count)
    return int(active_count), int(inactive_count), per_language


def build_admin_stats_text(translations: dict, language: str) -> str:
    active_count, inactive_count, per_language = get_subscriber_stats()
    lines = [
        t(translations, language, "admin_stats_header").format(
            active=active_count,
            unsubscribed=inactive_count,
        ),
        t(translations, language, "admin_stats_languages_header"),
    ]
    if not per_language:
        lines.append(t(translations, language, "admin_stats_languages_none"))
    else:
        for code, count in per_language.items():
            label = format_language_label(code)
            lines.append(f"- {label}: {count}")
    return "\n".join(lines)


def format_new_subscriber_message(
    translations: dict,
    language: str,
    user: Union[Message, CallbackQuery],
    chosen_language: str,
) -> str:
    from_user = user.from_user
    username = getattr(from_user, "username", None) if from_user else None
    first_name = getattr(from_user, "first_name", "") if from_user else ""
    last_name = getattr(from_user, "last_name", "") if from_user else ""
    if username:
        display = f"@{username}"
    else:
        display = " ".join(part for part in [first_name, last_name] if part).strip()
    display = display or t(translations, language, "admin_new_subscriber_unknown")
    label = format_language_label(chosen_language)
    return t(translations, language, "admin_new_subscriber").format(
        user=display,
        user_id=from_user.id if from_user else "unknown",
        language=label,
    )


async def cmd_start(message: Message, config: AppConfig) -> None:
    if not message.from_user:
        return

    translations = load_translations()
    user_id = message.from_user.id
    if not user_exists(user_id):
        await message.answer(
            t(translations, DEFAULT_LANGUAGE, "lng_prompt"),
            reply_markup=build_language_keyboard(),
        )
        return
    if not is_user_active(user_id):
        set_user_status(user_id, True)
    language = get_or_create_user_language(user_id)
    config = load_bot_config()
    await message.answer(
        build_start_message(translations, language),
        reply_markup=build_main_keyboard(translations, language, config),
    )


async def send_prediction(message: Message, user_id: int) -> None:
    translations = load_translations()
    language = get_or_create_user_language(user_id)
    try:
        image_path = get_random_image()
    except FileNotFoundError:
        await message.answer(t(translations, language, "predict_no_images"))
        return

    config = load_bot_config()
    keyboard = build_links_keyboard(config, translations, language)
    caption = build_prediction_caption(image_path, translations, language)

    await message.answer_photo(
        photo=FSInputFile(str(image_path)),
        caption=caption,
        reply_markup=keyboard,
    )

async def cmd_predict(message: Message) -> None:
    if not message.from_user:
        return
    await send_prediction(message, message.from_user.id)


async def on_next_prediction(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    if not callback.from_user:
        return
    translations = load_translations()
    language = get_user_language(callback.from_user.id)

    try:
        image_path = get_random_image()
    except FileNotFoundError:
        await callback.message.answer(t(translations, language, "predict_no_images"))
        await callback.answer()
        return

    config = load_bot_config()
    keyboard = build_links_keyboard(config, translations, language)
    caption = build_prediction_caption(image_path, translations, language)

    await callback.message.answer_photo(
        photo=FSInputFile(str(image_path)),
        caption=caption,
        reply_markup=keyboard,
    )
    await callback.answer()

async def on_get_prediction(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    await send_prediction(callback.message, callback.from_user.id)
    await callback.answer()


async def cmd_broadcast(message: Message, command: CommandObject, config: AppConfig) -> None:
    translations = load_translations()
    language = DEFAULT_LANGUAGE
    if message.from_user:
        language = get_user_language(message.from_user.id)
    if not is_admin(message, config):
        await message.answer(t(translations, language, "admin_only"))
        return

    text = command.args
    if not text:
        await message.answer(t(translations, language, "broadcast_usage"))
        return

    subscribers = load_subscribers()
    if not subscribers:
        await message.answer(t(translations, language, "broadcast_none"))
        return

    sent = 0
    failed = 0
    for user_id in subscribers:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except TelegramForbiddenError:
            set_user_status(user_id, False)
            failed += 1
        except Exception:
            failed += 1

    result_text = t(translations, language, "broadcast_done").format(
        sent=sent,
        failed=failed,
    )
    await message.answer(result_text)
    for admin_id in config.admin_ids:
        if message.from_user and admin_id == message.from_user.id:
            continue
        try:
            await message.bot.send_message(admin_id, result_text)
        except Exception:
            continue


async def cmd_setlink(message: Message, command: CommandObject, config: AppConfig) -> None:
    translations = load_translations()
    language = DEFAULT_LANGUAGE
    if message.from_user:
        language = get_user_language(message.from_user.id)
    if not is_admin(message, config):
        await message.answer(t(translations, language, "admin_only"))
        return

    new_link = (command.args or "").strip()
    if not new_link:
        await message.answer(t(translations, language, "setlink_usage"))
        return

    current = load_bot_config()
    current["affiliate_link"] = new_link
    save_bot_config(current)

    await message.answer(t(translations, language, "setlink_done"))


async def cmd_setcontact(message: Message, command: CommandObject, config: AppConfig) -> None:
    translations = load_translations()
    language = DEFAULT_LANGUAGE
    if message.from_user:
        language = get_user_language(message.from_user.id)
    if not is_admin(message, config):
        await message.answer(t(translations, language, "admin_only"))
        return

    new_link = (command.args or "").strip()
    if not new_link:
        await message.answer(t(translations, language, "setcontact_usage"))
        return

    current = load_bot_config()
    current["contact_link"] = new_link
    save_bot_config(current)

    await message.answer(t(translations, language, "setcontact_done"))


async def cmd_language(message: Message) -> None:
    if not message.from_user:
        return
    translations = load_translations()
    language = get_user_language(message.from_user.id)
    await message.answer(
        t(translations, language, "lng_prompt"),
        reply_markup=build_language_keyboard(),
    )

async def on_change_language(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    translations = load_translations()
    language = get_user_language(callback.from_user.id)
    await callback.message.answer(
        t(translations, language, "lng_prompt"),
        reply_markup=build_language_keyboard(),
    )
    await callback.answer()

async def on_show_start(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    translations = load_translations()
    language = get_or_create_user_language(callback.from_user.id)
    config = load_bot_config()
    await callback.message.answer(
        build_start_message(translations, language),
        reply_markup=build_main_keyboard(translations, language, config),
    )
    await callback.answer()


async def on_set_language(callback: CallbackQuery, config: AppConfig) -> None:
    if not callback.message or not callback.from_user:
        return
    data = callback.data or ""
    _, _, code = data.partition(":")
    if code not in LANGUAGES:
        await callback.answer()
        return
    is_new = upsert_user_language(callback.from_user.id, code)
    translations = load_translations()
    flag = LANGUAGE_FLAGS.get(code, "")
    label = f"{flag} {LANGUAGES[code]}".strip()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        t(translations, code, "lng_updated").format(language=label)
    )
    await callback.message.answer(
        build_start_message(translations, code),
        reply_markup=build_main_keyboard(translations, code, load_bot_config()),
    )
    if is_new:
        bot_config = load_bot_config()
        if get_bool_config(bot_config, "notify_new_subscribers", False):
            admin_language = DEFAULT_LANGUAGE
            text = format_new_subscriber_message(translations, admin_language, callback, code)
            for admin_id in config.admin_ids:
                try:
                    await callback.bot.send_message(admin_id, text)
                except Exception:
                    continue
    await callback.answer()


async def cmd_stop(message: Message) -> None:
    if not message.from_user:
        return
    translations = load_translations()
    language = get_or_create_user_language(message.from_user.id)
    set_user_status(message.from_user.id, False)
    await message.answer(t(translations, language, "unsubscribed"))


async def cmd_admin(message: Message, config: AppConfig) -> None:
    translations = load_translations()
    language = DEFAULT_LANGUAGE
    if message.from_user:
        language = get_user_language(message.from_user.id)
    if not is_admin(message, config):
        await message.answer(t(translations, language, "admin_only"))
        return
    bot_config = load_bot_config()
    notify_enabled = get_bool_config(bot_config, "notify_new_subscribers", False)
    stats_text = build_admin_stats_text(translations, language)
    await message.answer(
        stats_text,
        reply_markup=build_admin_keyboard(translations, language, notify_enabled),
    )


async def on_admin_action(callback: CallbackQuery, config: AppConfig) -> None:
    if not callback.message or not callback.from_user:
        return
    translations = load_translations()
    language = get_user_language(callback.from_user.id)
    if not is_admin_user(callback.from_user.id, config):
        await callback.answer(t(translations, language, "admin_only"), show_alert=True)
        return
    action = (callback.data or "").split(":", 1)[-1]
    bot_config = load_bot_config()
    if action == "toggle_notify":
        current = get_bool_config(bot_config, "notify_new_subscribers", False)
        bot_config["notify_new_subscribers"] = "true" if not current else "false"
        save_bot_config(bot_config)
        notice_key = "admin_notify_enabled" if not current else "admin_notify_disabled"
        await callback.answer(t(translations, language, notice_key))
    else:
        await callback.answer()
    notify_enabled = get_bool_config(load_bot_config(), "notify_new_subscribers", False)
    stats_text = build_admin_stats_text(translations, language)
    await callback.message.edit_text(
        stats_text,
        reply_markup=build_admin_keyboard(translations, language, notify_enabled),
    )


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

    async def cmd_admin_entry(message: Message) -> None:
        await cmd_admin(message, app_config)

    async def on_admin_action_entry(callback: CallbackQuery) -> None:
        await on_admin_action(callback, app_config)

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
    dp.message.register(cmd_admin_entry, Command("admin"))
    dp.message.register(cmd_stop, Command("stop"))
    dp.message.register(cmd_language, Command("lng"))
    dp.callback_query.register(on_next_prediction, F.data == "next_prediction")
    dp.callback_query.register(on_get_prediction, F.data == "get_prediction")
    dp.callback_query.register(on_change_language, F.data == "change_language")
    dp.callback_query.register(on_show_start, F.data == "show_start")
    async def on_set_language_entry(callback: CallbackQuery) -> None:
        await on_set_language(callback, app_config)

    dp.callback_query.register(on_set_language_entry, F.data.startswith("set_lang:"))
    dp.callback_query.register(
        on_admin_action_entry,
        F.data.startswith("admin:"),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
