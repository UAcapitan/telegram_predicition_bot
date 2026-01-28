import asyncio
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F
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
}

LANGUAGES = {
    "en": "English",
    "pl": "Polish",
    "sr": "Serbian",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
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

DEFAULT_TRANSLATIONS = {
    "en": {
        "start_user": (
            "Welcome! I send random prediction images.\n\n"
            "Commands:\n"
            "/predict - get a random prediction\n"
            "/start - show this help\n"
            "/lng - change language"
        ),
        "start_admin": (
            "Admin commands:\n"
            "/broadcast your message - send to all subscribers\n"
            "/setlink https://your-link - update affiliate link\n"
            "/setcontact https://t.me/your_contact - update contact link"
        ),
        "admin_only": "Admin only.",
        "predict_no_images": "No prediction images yet. Add files to data/images.",
        "broadcast_usage": "Usage: /broadcast your message",
        "broadcast_none": "No subscribers yet.",
        "broadcast_done": "Broadcast complete. Sent: {sent}, Failed: {failed}.",
        "setlink_usage": "Usage: /setlink https://your-link",
        "setlink_done": "Affiliate link updated.",
        "setcontact_usage": "Usage: /setcontact https://t.me/your_contact",
        "setcontact_done": "Contact link updated.",
        "lng_prompt": "Choose your language:",
        "lng_updated": "Language updated to {language}.",
        "prediction_default": "Your prediction is ready!",
        "prediction_format": (
            "Difficulty: {difficulty}\n"
            "Multiplier: up to {value}x\n"
            "Cashout: {value}x or before"
        ),
        "button_next": "Next prediction",
        "button_start": "Start playing",
        "button_support": "Support",
    },
    "pl": {
        "start_user": (
            "Witaj! Wysyłam losowe obrazy z prognozami.\n\n"
            "Komendy:\n"
            "/predict - losowa prognoza\n"
            "/start - pokaż pomoc\n"
            "/lng - zmień język"
        ),
        "start_admin": (
            "Komendy administratora:\n"
            "/broadcast twoja wiadomość - wyślij do wszystkich\n"
            "/setlink https://twoj-link - ustaw link partnerski\n"
            "/setcontact https://t.me/twoj_kontakt - ustaw kontakt"
        ),
        "admin_only": "Tylko dla administratora.",
        "predict_no_images": "Brak obrazów z prognozami. Dodaj pliki do data/images.",
        "broadcast_usage": "Użycie: /broadcast twoja wiadomość",
        "broadcast_none": "Brak subskrybentów.",
        "broadcast_done": "Wysyłka zakończona. Wysłane: {sent}, Błędy: {failed}.",
        "setlink_usage": "Użycie: /setlink https://twoj-link",
        "setlink_done": "Link partnerski zaktualizowany.",
        "setcontact_usage": "Użycie: /setcontact https://t.me/twoj_kontakt",
        "setcontact_done": "Kontakt zaktualizowany.",
        "lng_prompt": "Wybierz język:",
        "lng_updated": "Język ustawiony na {language}.",
        "prediction_default": "Twoja prognoza jest gotowa!",
        "prediction_format": (
            "Poziom: {difficulty}\n"
            "Mnożnik: do {value}x\n"
            "Wypłata: {value}x lub wcześniej"
        ),
        "button_next": "Następna prognoza",
        "button_start": "Zacznij grać",
        "button_support": "Wsparcie",
    },
    "sr": {
        "start_user": (
            "Zdravo! Šaljem nasumične slike predikcija.\n\n"
            "Komande:\n"
            "/predict - nasumična predikcija\n"
            "/start - prikaži pomoć\n"
            "/lng - promeni jezik"
        ),
        "start_admin": (
            "Admin komande:\n"
            "/broadcast tvoja poruka - pošalji svima\n"
            "/setlink https://tvoj-link - postavi affiliate link\n"
            "/setcontact https://t.me/tvoj_kontakt - postavi kontakt"
        ),
        "admin_only": "Samo za administratore.",
        "predict_no_images": "Nema slika predikcija. Dodaj fajlove u data/images.",
        "broadcast_usage": "Upotreba: /broadcast tvoja poruka",
        "broadcast_none": "Nema pretplatnika.",
        "broadcast_done": "Slanje završeno. Poslato: {sent}, Neuspešno: {failed}.",
        "setlink_usage": "Upotreba: /setlink https://tvoj-link",
        "setlink_done": "Affiliate link je ažuriran.",
        "setcontact_usage": "Upotreba: /setcontact https://t.me/tvoj_kontakt",
        "setcontact_done": "Kontakt je ažuriran.",
        "lng_prompt": "Izaberi jezik:",
        "lng_updated": "Jezik je postavljen na {language}.",
        "prediction_default": "Tvoja predikcija je spremna!",
        "prediction_format": (
            "Težina: {difficulty}\n"
            "Multiplikator: do {value}x\n"
            "Isplata: {value}x ili ranije"
        ),
        "button_next": "Sledeća predikcija",
        "button_start": "Počni igranje",
        "button_support": "Podrška",
    },
    "fr": {
        "start_user": (
            "Bienvenue ! J’envoie des images de prédictions aléatoires.\n\n"
            "Commandes :\n"
            "/predict - prédiction aléatoire\n"
            "/start - afficher l’aide\n"
            "/lng - changer la langue"
        ),
        "start_admin": (
            "Commandes admin :\n"
            "/broadcast votre message - envoyer à tous\n"
            "/setlink https://votre-lien - définir le lien d’affiliation\n"
            "/setcontact https://t.me/votre_contact - définir le contact"
        ),
        "admin_only": "Réservé aux administrateurs.",
        "predict_no_images": "Aucune image de prédiction. Ajoutez des fichiers dans data/images.",
        "broadcast_usage": "Utilisation : /broadcast votre message",
        "broadcast_none": "Aucun abonné.",
        "broadcast_done": "Diffusion terminée. Envoyés : {sent}, Échecs : {failed}.",
        "setlink_usage": "Utilisation : /setlink https://votre-lien",
        "setlink_done": "Lien d’affiliation mis à jour.",
        "setcontact_usage": "Utilisation : /setcontact https://t.me/votre_contact",
        "setcontact_done": "Contact mis à jour.",
        "lng_prompt": "Choisissez votre langue :",
        "lng_updated": "Langue mise à jour : {language}.",
        "prediction_default": "Votre prédiction est prête !",
        "prediction_format": (
            "Difficulté : {difficulty}\n"
            "Multiplicateur : jusqu’à {value}x\n"
            "Encaissement : {value}x ou avant"
        ),
        "button_next": "Prédiction suivante",
        "button_start": "Commencer",
        "button_support": "Support",
    },
    "es": {
        "start_user": (
            "¡Bienvenido! Envío imágenes de predicciones aleatorias.\n\n"
            "Comandos:\n"
            "/predict - predicción aleatoria\n"
            "/start - mostrar ayuda\n"
            "/lng - cambiar idioma"
        ),
        "start_admin": (
            "Comandos de admin:\n"
            "/broadcast tu mensaje - enviar a todos\n"
            "/setlink https://tu-link - actualizar enlace afiliado\n"
            "/setcontact https://t.me/tu_contacto - actualizar contacto"
        ),
        "admin_only": "Solo para administradores.",
        "predict_no_images": "No hay imágenes de predicciones. Agrega archivos en data/images.",
        "broadcast_usage": "Uso: /broadcast tu mensaje",
        "broadcast_none": "No hay suscriptores.",
        "broadcast_done": "Envío completo. Enviados: {sent}, Fallidos: {failed}.",
        "setlink_usage": "Uso: /setlink https://tu-link",
        "setlink_done": "Enlace afiliado actualizado.",
        "setcontact_usage": "Uso: /setcontact https://t.me/tu_contacto",
        "setcontact_done": "Contacto actualizado.",
        "lng_prompt": "Elige tu idioma:",
        "lng_updated": "Idioma actualizado a {language}.",
        "prediction_default": "¡Tu predicción está lista!",
        "prediction_format": (
            "Dificultad: {difficulty}\n"
            "Multiplicador: hasta {value}x\n"
            "Cobro: {value}x o antes"
        ),
        "button_next": "Siguiente predicción",
        "button_start": "Empezar a jugar",
        "button_support": "Soporte",
    },
    "de": {
        "start_user": (
            "Willkommen! Ich sende zufällige Vorhersagebilder.\n\n"
            "Befehle:\n"
            "/predict - zufällige Vorhersage\n"
            "/start - Hilfe anzeigen\n"
            "/lng - Sprache ändern"
        ),
        "start_admin": (
            "Admin-Befehle:\n"
            "/broadcast deine Nachricht - an alle senden\n"
            "/setlink https://dein-link - Affiliate-Link setzen\n"
            "/setcontact https://t.me/dein_kontakt - Kontakt setzen"
        ),
        "admin_only": "Nur für Admins.",
        "predict_no_images": "Keine Vorhersagebilder vorhanden. Füge Dateien zu data/images hinzu.",
        "broadcast_usage": "Verwendung: /broadcast deine Nachricht",
        "broadcast_none": "Keine Abonnenten.",
        "broadcast_done": "Broadcast abgeschlossen. Gesendet: {sent}, Fehlgeschlagen: {failed}.",
        "setlink_usage": "Verwendung: /setlink https://dein-link",
        "setlink_done": "Affiliate-Link aktualisiert.",
        "setcontact_usage": "Verwendung: /setcontact https://t.me/dein_kontakt",
        "setcontact_done": "Kontakt aktualisiert.",
        "lng_prompt": "Wähle deine Sprache:",
        "lng_updated": "Sprache aktualisiert auf {language}.",
        "prediction_default": "Deine Vorhersage ist bereit!",
        "prediction_format": (
            "Schwierigkeit: {difficulty}\n"
            "Multiplikator: bis {value}x\n"
            "Auszahlung: {value}x oder früher"
        ),
        "button_next": "Nächste Vorhersage",
        "button_start": "Jetzt spielen",
        "button_support": "Support",
    },
    "it": {
        "start_user": (
            "Benvenuto! Invio immagini di previsioni casuali.\n\n"
            "Comandi:\n"
            "/predict - previsione casuale\n"
            "/start - mostra aiuto\n"
            "/lng - cambia lingua"
        ),
        "start_admin": (
            "Comandi admin:\n"
            "/broadcast il tuo messaggio - invia a tutti\n"
            "/setlink https://tuo-link - aggiorna link affiliato\n"
            "/setcontact https://t.me/tuo_contatto - aggiorna contatto"
        ),
        "admin_only": "Solo per amministratori.",
        "predict_no_images": "Nessuna immagine di previsione. Aggiungi file in data/images.",
        "broadcast_usage": "Uso: /broadcast il tuo messaggio",
        "broadcast_none": "Nessun iscritto.",
        "broadcast_done": "Invio completato. Inviati: {sent}, Falliti: {failed}.",
        "setlink_usage": "Uso: /setlink https://tuo-link",
        "setlink_done": "Link affiliato aggiornato.",
        "setcontact_usage": "Uso: /setcontact https://t.me/tuo_contatto",
        "setcontact_done": "Contatto aggiornato.",
        "lng_prompt": "Scegli la tua lingua:",
        "lng_updated": "Lingua aggiornata a {language}.",
        "prediction_default": "La tua previsione è pronta!",
        "prediction_format": (
            "Difficoltà: {difficulty}\n"
            "Moltiplicatore: fino a {value}x\n"
            "Incasso: {value}x o prima"
        ),
        "button_next": "Prossima previsione",
        "button_start": "Inizia a giocare",
        "button_support": "Supporto",
    },
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
                f"""
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id BIGINT PRIMARY KEY,
                    lng TEXT NOT NULL DEFAULT '{DEFAULT_LANGUAGE}'
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
        TRANSLATIONS_FILE.write_text(
            json.dumps(DEFAULT_TRANSLATIONS, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    ensure_database()

def load_subscribers() -> set[int]:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM subscribers")
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


def get_or_create_user_language(user_id: int) -> str:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT lng FROM subscribers WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lng)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, DEFAULT_LANGUAGE),
            )
            return DEFAULT_LANGUAGE


def set_user_language(user_id: int, language: str) -> None:
    db_url = get_database_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lng)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET lng = EXCLUDED.lng
                """,
                (user_id, language),
            )


def load_translations() -> dict:
    if not TRANSLATIONS_FILE.exists():
        return DEFAULT_TRANSLATIONS
    try:
        data = json.loads(TRANSLATIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_TRANSLATIONS
    if not isinstance(data, dict):
        return DEFAULT_TRANSLATIONS
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

    builder.button(text=t(translations, language, "button_next"), callback_data="next_prediction")
    if affiliate:
        builder.button(text=t(translations, language, "button_start"), url=affiliate)
    if contact:
        builder.button(text=t(translations, language, "button_support"), url=contact)

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


def build_start_message(translations: dict, language: str) -> str:
    return t(translations, language, "start_user")


async def cmd_start(message: Message, config: AppConfig) -> None:
    if not message.from_user:
        return

    translations = load_translations()
    language = get_or_create_user_language(message.from_user.id)
    await message.answer(build_start_message(translations, language))


async def cmd_predict(message: Message) -> None:
    if not message.from_user:
        return
    translations = load_translations()
    language = get_or_create_user_language(message.from_user.id)
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


async def on_set_language(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    data = callback.data or ""
    _, _, code = data.partition(":")
    if code not in LANGUAGES:
        await callback.answer()
        return
    set_user_language(callback.from_user.id, code)
    translations = load_translations()
    await callback.message.answer(
        t(translations, code, "lng_updated").format(language=LANGUAGES[code])
    )
    await callback.answer()


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
    dp.message.register(cmd_language, Command("lng"))
    dp.callback_query.register(on_next_prediction, F.data == "next_prediction")
    dp.callback_query.register(on_set_language, F.data.startswith("set_lang:"))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
