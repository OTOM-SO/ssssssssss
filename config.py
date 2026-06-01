"""Загрузка конфигурации из переменных окружения (.env)."""

import base64
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

# Путь к ключу сервисного аккаунта. Относительный путь привязываем к папке с
# кодом, а не к текущей рабочей директории, — иначе при запуске бота из другого
# каталога файл «не находится» и календарь молча отключается.
_creds_raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
if os.path.isabs(_creds_raw):
    GOOGLE_CREDENTIALS_JSON = _creds_raw
else:
    GOOGLE_CREDENTIALS_JSON = os.path.join(os.path.dirname(__file__), _creds_raw)


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
    elif not os.path.exists(GOOGLE_CREDENTIALS_JSON):
        logger.warning(
            "Файл учётных данных Google '%s' не найден — "
            "события в Google Calendar создаваться не будут.",
            GOOGLE_CREDENTIALS_JSON,
        )
