"""Загрузка конфигурации из переменных окружения (.env)."""

import base64
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

# Загружаем .env из папки с кодом, а не из текущей рабочей директории, — иначе
# при запуске бота из другого каталога переменные (в т.ч. CALENDAR_ID) просто
# не подхватываются, и календарь молча отключается.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)


def _normalize_calendar_id(raw: str) -> str:
    """Приводит CALENDAR_ID к виду, который понимает Google Calendar API.

    Пользователь часто вставляет полную ссылку на календарь вида
    «https://calendar.google.com/calendar/u/1?cid=<base64>». API же ждёт
    идентификатор календаря (обычно e-mail). Достаём cid и декодируем его.
    """
    raw = raw.strip()
    if not raw or "calendar.google.com" not in raw:
        return raw

    cid_values = parse_qs(urlparse(raw).query).get("cid")
    if not cid_values:
        return raw

    cid = cid_values[0]
    # base64url может быть без выравнивающих «=» — дополняем перед декодированием.
    padded = cid + "=" * (-len(cid) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        logger.warning("Не удалось декодировать cid календаря из ссылки: %r", raw)
        return raw

    # Декодированное значение должно выглядеть как идентификатор календаря.
    if re.fullmatch(r"[^@\s]+@[^@\s]+", decoded) or "group.calendar.google.com" in decoded:
        return decoded
    return decoded


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WORK_CHAT_ID = os.getenv("WORK_CHAT_ID", "")
CALENDAR_ID = _normalize_calendar_id(os.getenv("CALENDAR_ID", ""))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Путь к файлу ключа сервисного аккаунта — для локальной разработки, когда
# credentials.json лежит рядом с кодом. Относительный путь привязываем к папке с
# кодом, а не к текущей рабочей директории, — иначе при запуске бота из другого
# каталога файл «не находится» и календарь молча отключается.
_creds_raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
if os.path.isabs(_creds_raw):
    GOOGLE_CREDENTIALS_JSON = _creds_raw
else:
    GOOGLE_CREDENTIALS_JSON = os.path.join(os.path.dirname(__file__), _creds_raw)


def _load_google_credentials_info() -> dict | None:
    """Данные сервисного аккаунта Google как dict (или None, если ключа нет).

    Ключ загружается ПРЯМО В ПАМЯТЬ — файл на диск не пишется. Это надёжно
    работает на хостингах с эфемерной/только-для-чтения файловой системой
    (Railway, Heroku и т.п.), где диск обнуляется после каждого деплоя.

    Источники в порядке приоритета:
    1. GOOGLE_CREDENTIALS_JSON_B64 — содержимое credentials.json, закодированное
       в base64 (base64 берём, чтобы переносы строк в приватном ключе не ломались
       в UI переменных окружения). Задаётся один раз — больше обновлять ничего не
       надо.
    2. Файл по пути GOOGLE_CREDENTIALS_JSON — для локальной разработки.
    """
    b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_B64", "").strip()
    if b64:
        try:
            raw = base64.b64decode(b64).decode("utf-8")
            return json.loads(raw)
        except Exception:
            logger.exception(
                "GOOGLE_CREDENTIALS_JSON_B64 задана, но её не удалось разобрать — "
                "ожидается base64 от содержимого credentials.json. "
                "Google Calendar будет отключён."
            )
            return None

    if os.path.exists(GOOGLE_CREDENTIALS_JSON):
        try:
            with open(GOOGLE_CREDENTIALS_JSON, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logger.exception(
                "Не удалось прочитать файл ключа Google %s. "
                "Google Calendar будет отключён.",
                GOOGLE_CREDENTIALS_JSON,
            )
            return None

    return None


# Данные сервисного аккаунта, загруженные один раз при старте. None — ключа нет.
GOOGLE_CREDENTIALS_INFO = _load_google_credentials_info()


def google_credentials_available() -> bool:
    """Есть ли ключ сервисного аккаунта Google (из base64-переменной или файла)."""
    return GOOGLE_CREDENTIALS_INFO is not None


def validate_config() -> None:
    """Проверяет наличие обязательных переменных. Бросает RuntimeError при ошибке."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not WORK_CHAT_ID:
        missing.append("WORK_CHAT_ID")
    if missing:
        raise RuntimeError(
            "Не заданы обязательные переменные окружения: "
            + ", ".join(missing)
            + ". Заполните файл .env (см. .env.example)."
        )

    if not CALENDAR_ID:
        logger.warning(
            "CALENDAR_ID не задан — события в Google Calendar создаваться не будут."
        )
    elif not google_credentials_available():
        logger.warning(
            "Учётные данные Google не заданы (ни GOOGLE_CREDENTIALS_JSON_B64, "
            "ни файл '%s') — события в Google Calendar создаваться не будут.",
            GOOGLE_CREDENTIALS_JSON,
        )
