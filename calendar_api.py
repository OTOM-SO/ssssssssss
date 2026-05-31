"""Создание событий в Google Calendar через сервисный аккаунт."""

import asyncio
import datetime
import logging
import os
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import CALENDAR_ID, GOOGLE_CREDENTIALS_JSON, TIMEZONE

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Разделитель времени может быть обычным дефисом или тире (– —).
_TIME_RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$"
)


def calendar_enabled() -> bool:
    """Доступна ли интеграция с Google Calendar (есть конфиг и файл ключа)."""
    return bool(CALENDAR_ID) and os.path.exists(GOOGLE_CREDENTIALS_JSON)


def _build_service():
    """Создаёт клиент Google Calendar API (синхронно)."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_JSON, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _parse_datetimes(date_str: str, time_str: str):
    """Преобразует «ДД.ММ.ГГГГ» и «ЧЧ:ММ–ЧЧ:ММ» в (start, end) datetime.

    Если конец раньше начала (мероприятие через полночь) — конец переносится
    на следующий день.
    """
    day, month, year = (int(p) for p in date_str.split("."))
    match = _TIME_RANGE_RE.match(time_str)
    if not match:
        raise ValueError(f"Не удалось разобрать время: {time_str!r}")

    sh, sm, eh, em = (int(g) for g in match.groups())
    start = datetime.datetime(year, month, day, sh, sm)
    end = datetime.datetime(year, month, day, eh, em)
    if end <= start:
        end += datetime.timedelta(days=1)
    return start, end


def _create_event_sync(
    summary: str,
    description: str,
    location: str,
    date_str: str,
    time_str: str,
) -> str:
    """Создаёт событие и возвращает ссылку на него (htmlLink)."""
    start, end = _parse_datetimes(date_str, time_str)
    service = _build_service()
    event_body = {
        "summary": summary,
        "location": location,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
    }
    event = (
        service.events()
        .insert(calendarId=CALENDAR_ID, body=event_body)
        .execute()
    )
    link = event.get("htmlLink", "")
    logger.info("Событие создано в Google Calendar: %s", link)
    return link


async def create_event(
    summary: str,
    description: str,
    location: str,
    date_str: str,
    time_str: str,
) -> str:
    """Асинхронная обёртка: создаёт событие в Google Calendar.

    Блокирующий вызов API выполняется в отдельном потоке, чтобы не
    блокировать event loop. Возвращает htmlLink созданного события.
    """
    return await asyncio.to_thread(
        _create_event_sync, summary, description, location, date_str, time_str
    )
