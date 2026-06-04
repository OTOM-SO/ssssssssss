"""Точка входа: настройка логирования и запуск Telegram-бота."""

import logging

from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

import calendar_api
import config
from handlers import build_conversation_handler, chat_id_command, help_command

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Лишний шум от HTTP-библиотеки приглушаем.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок.

    Без него любая ошибка (включая сетевые) валится полным трейсбеком в лог.
    Конфликт getUpdates на Railway почти всегда означает короткое наложение
    деплоев (новый контейнер уже поднят, старый ещё не погашен) — пишем одну
    понятную строку вместо простыни и не считаем это аварией.
    """
    error = context.error
    if isinstance(error, Conflict):
        logger.warning(
            "Conflict getUpdates: с этим токеном опрашивает обновления другая "
            "копия бота. Обычно это переходное наложение деплоев и проходит "
            "само; если повторяется — проверь, что запущен ровно один экземпляр."
        )
        return

    logger.error("Необработанная ошибка при обработке обновления: %s", error, exc_info=error)


def main() -> None:
    config.validate_config()

    if calendar_api.calendar_enabled():
        # Проверяем доступ к календарю сразу при старте, а не молча падаем
        # во время первой заявки. Так проблема с ключом или доступом видна
        # в логах немедленно.
        ok, message = calendar_api.check_access()
        if ok:
            logger.info(
                "Google Calendar подключён (%s, календарь %s).",
                message,
                config.CALENDAR_ID,
            )
        else:
            logger.warning(
                "Google Calendar НЕ работает: %s. "
                "Заявки будут уходить в чат, но события создаваться НЕ будут, "
                "пока проблема не устранена.",
                message,
            )
    else:
        logger.warning(
            "Google Calendar отключён (CALENDAR_ID=%r, ключ: %s). "
            "События сохраняться НЕ будут.",
            config.CALENDAR_ID,
            "найден" if config.google_credentials_available() else "не найден",
        )

    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(build_conversation_handler())
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("chatid", chat_id_command))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен. Ожидание сообщений...")
    # drop_pending_updates: при перезапуске не доедаем накопившуюся за простой
    # очередь обновлений, чтобы бот не отвечал на устаревшие сообщения.
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
