"""Точка входа: настройка логирования и запуск Telegram-бота."""

import logging
import os

from telegram.ext import Application, CommandHandler

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


def main() -> None:
    config.validate_config()

    if calendar_api.calendar_enabled():
        logger.info(
            "Google Calendar подключён: события будут сохраняться в календарь %s.",
            config.CALENDAR_ID,
        )
    else:
        logger.warning(
            "Google Calendar отключён (CALENDAR_ID=%r, ключ: %s). "
            "События сохраняться НЕ будут.",
            config.CALENDAR_ID,
            "найден" if os.path.exists(config.GOOGLE_CREDENTIALS_JSON) else "не найден",
        )

    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(build_conversation_handler())
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("chatid", chat_id_command))

    logger.info("Бот запущен. Ожидание сообщений...")
    application.run_polling()


if __name__ == "__main__":
    main()
