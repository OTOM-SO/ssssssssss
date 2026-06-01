"""Диалог приёма заявки на техсопровождение (ConversationHandler)."""

import datetime
import logging
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import calendar_api
from config import WORK_CHAT_ID

logger = logging.getLogger(__name__)

# Состояния диалога
(
    FULL_NAME,
    CONTACT,
    EVENT_NAME,
    DEPARTMENT,
    DATE,
    TIME,
    VENUE,
    DESCRIPTION,
    LAPTOP,
    CONFIRM,
) = range(10)

# Разделитель диапазона времени: дефис или тире.
_TIME_RANGE_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$")

# Тексты постоянных кнопок («горячих клавиш») под полем ввода.
NEW_REQUEST_BTN = "📝 Новая заявка"
FINISH_BTN = "🛑 Завершить"

# Регэксп, которым ConversationHandler ловит нажатия этих кнопок.
_BUTTON_RE = re.compile(f"^({re.escape(NEW_REQUEST_BTN)}|{re.escape(FINISH_BTN)})$")


# --- Вспомогательные функции ----------------------------------------------


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура с кнопками запуска и завершения заявки."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(NEW_REQUEST_BTN), KeyboardButton(FINISH_BTN)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def _laptop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Да", callback_data="laptop_yes"),
                InlineKeyboardButton("❌ Нет", callback_data="laptop_no"),
            ]
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Отправить", callback_data="confirm_send")],
            [InlineKeyboardButton("✏️ Заполнить заново", callback_data="confirm_restart")],
        ]
    )


def _build_summary(data: dict) -> str:
    """Формирует итоговое сообщение в Markdown."""
    return (
        "📋 *ЗАЯВКА НА ТЕХСОПРОВОЖДЕНИЕ*\n\n"
        f"👤 *Организатор:* {data['full_name']}\n"
        f"📞 *Контакт:* {data['contact']}\n\n"
        f"🎪 *Мероприятие:* {data['event_name']}\n"
        f"🏢 *Подразделение:* {data['department']}\n"
        f"📅 *Дата:* {data['date']}\n"
        f"⏰ *Время:* {data['time']}\n"
        f"📍 *Площадка:* {data['venue']}\n\n"
        "🎛 *Техсопровождение:*\n"
        f"{data['description']}\n\n"
        f"💻 *Ноутбук организатора:* {data['laptop']}"
    )


def _build_plain_summary(data: dict) -> str:
    """Тот же итог, но без Markdown — для описания события в календаре."""
    return (
        "ЗАЯВКА НА ТЕХСОПРОВОЖДЕНИЕ\n\n"
        f"Организатор: {data['full_name']}\n"
        f"Контакт: {data['contact']}\n\n"
        f"Мероприятие: {data['event_name']}\n"
        f"Подразделение: {data['department']}\n"
        f"Дата: {data['date']}\n"
        f"Время: {data['time']}\n"
        f"Площадка: {data['venue']}\n\n"
        "Техсопровождение:\n"
        f"{data['description']}\n\n"
        f"Ноутбук организатора: {data['laptop']}"
    )


# --- Шаги диалога ----------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Здравствуйте! Это бот для приёма заявок на техническое "
        "сопровождение мероприятий.\n\n"
        "Я задам несколько вопросов по очереди. В любой момент можно "
        "прервать заполнение командой /cancel.\n\n"
        "1️⃣ Укажите *ФИО организатора*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_main_keyboard(),
    )
    return FULL_NAME


async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["full_name"] = update.message.text.strip()
    await update.message.reply_text(
        "2️⃣ Укажите *контакт организатора* (телефон / Telegram / ВКонтакте) "
        "одним сообщением:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["contact"] = update.message.text.strip()
    await update.message.reply_text(
        "3️⃣ Укажите *название мероприятия*:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return EVENT_NAME


async def event_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_name"] = update.message.text.strip()
    await update.message.reply_text(
        "4️⃣ Укажите *подразделение*:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DEPARTMENT


async def department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["department"] = update.message.text.strip()
    await update.message.reply_text(
        "5️⃣ Укажите *дату мероприятия* в формате ДД.ММ.ГГГГ (например, 15.06.2026):",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DATE


async def date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        parsed = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "⚠️ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ "
            "(например, 15.06.2026):"
        )
        return DATE

    # Нормализуем к каноничному виду с ведущими нулями.
    context.user_data["date"] = parsed.strftime("%d.%m.%Y")
    await update.message.reply_text(
        "6️⃣ Укажите *время занятости* в формате ЧЧ:ММ–ЧЧ:ММ "
        "(например, 16:00–20:00):",
        parse_mode=ParseMode.MARKDOWN,
    )
    return TIME


async def time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    match = _TIME_RANGE_RE.match(text)
    if not match:
        await update.message.reply_text(
            "⚠️ Неверный формат времени. Введите диапазон в формате "
            "ЧЧ:ММ–ЧЧ:ММ (например, 16:00–20:00):"
        )
        return TIME

    sh, sm, eh, em = (int(g) for g in match.groups())
    if not (0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59):
        await update.message.reply_text(
            "⚠️ Часы должны быть в диапазоне 0–23, минуты 0–59. "
            "Введите время повторно (например, 16:00–20:00):"
        )
        return TIME

    # Сохраняем в каноничном виде с обычным тире.
    context.user_data["time"] = f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}"
    await update.message.reply_text(
        "7️⃣ Укажите *площадку* (адрес или аудитория):",
        parse_mode=ParseMode.MARKDOWN,
    )
    return VENUE


async def venue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["venue"] = update.message.text.strip()
    await update.message.reply_text(
        "8️⃣ Опишите *необходимое техсопровождение*.\n\n"
        "_Например: концерт, 2 гитары, вокал — нужен звук и вывод "
        "изображения на экран._",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DESCRIPTION


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text(
        "9️⃣ Будет ли у организаторов *ноутбук*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_laptop_keyboard(),
    )
    return LAPTOP


async def laptop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["laptop"] = "Да" if query.data == "laptop_yes" else "Нет"

    summary = _build_summary(context.user_data)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        summary + "\n\n──────────\nПроверьте заявку и подтвердите отправку:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_confirm_keyboard(),
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_restart":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🔄 Хорошо, начнём заново. Укажите *ФИО организатора*:",
            parse_mode=ParseMode.MARKDOWN,
        )
        data = context.user_data
        data.clear()
        return FULL_NAME

    # confirm_send
    data = context.user_data
    summary = _build_summary(data)
    await query.edit_message_reply_markup(reply_markup=None)

    # 1. Отправляем заявку в рабочий чат.
    try:
        await context.bot.send_message(
            chat_id=WORK_CHAT_ID,
            text=summary,
            parse_mode=ParseMode.MARKDOWN,
        )
        sent_ok = True
    except Exception:
        logger.exception("Не удалось отправить заявку в рабочий чат")
        sent_ok = False

    # 2. Создаём событие в Google Calendar (не критично).
    calendar_note = ""
    if calendar_api.calendar_enabled():
        try:
            link = await calendar_api.create_event(
                summary=data["event_name"],
                description=_build_plain_summary(data),
                location=data["venue"],
                date_str=data["date"],
                time_str=data["time"],
            )
            calendar_note = f"\n📆 Событие добавлено в календарь: {link}" if link else ""
        except Exception:
            logger.exception("Ошибка при создании события в Google Calendar")
            calendar_note = (
                "\n⚠️ Заявка принята, но событие в Google Calendar создать "
                "не удалось. Сообщите технической команде."
            )

    if sent_ok:
        await query.message.reply_text(
            "✅ Спасибо! Ваша заявка отправлена технической команде." + calendar_note
        )
    else:
        await query.message.reply_text(
            "⚠️ Не удалось отправить заявку в рабочий чат. "
            "Пожалуйста, свяжитесь с технической командой напрямую." + calendar_note
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Заполнение заявки отменено. Чтобы начать заново, нажмите "
        f"«{NEW_REQUEST_BTN}» или отправьте /start.",
        reply_markup=_main_keyboard(),
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ *О боте*\n\n"
        "Этот бот принимает заявки на техническое сопровождение "
        "мероприятий. Он по очереди задаст вопросы об организаторе, "
        "мероприятии, дате, времени, площадке и нужном оборудовании, "
        "а затем отправит заявку технической команде и добавит событие "
        "в общий календарь.\n\n"
        "*Кнопки под полем ввода:*\n"
        f"«{NEW_REQUEST_BTN}» — начать новую заявку\n"
        f"«{FINISH_BTN}» — завершить заполнение\n\n"
        "*Команды:*\n"
        "/start — начать новую заявку\n"
        "/cancel — отменить заполнение\n"
        "/help — это сообщение",
        parse_mode=ParseMode.MARKDOWN,
    )


async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ID текущего чата — нужен для настройки WORK_CHAT_ID."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"ID этого чата: `{chat.id}`\n"
        f"Тип: {chat.type}\n\n"
        "Скопируйте число (вместе со знаком «−») в переменную "
        "WORK_CHAT_ID в файле .env.",
        parse_mode=ParseMode.MARKDOWN,
    )


def build_conversation_handler() -> ConversationHandler:
    """Собирает ConversationHandler со всеми шагами диалога."""
    # Текст обычных ответов: не команда и не нажатие постоянных кнопок —
    # иначе «🛑 Завершить» попало бы, например, в поле ФИО.
    button_filter = filters.Regex(_BUTTON_RE)
    text_only = filters.TEXT & ~filters.COMMAND & ~button_filter
    new_request_filter = filters.Regex(f"^{re.escape(NEW_REQUEST_BTN)}$")
    finish_filter = filters.Regex(f"^{re.escape(FINISH_BTN)}$")
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(new_request_filter, start),
        ],
        states={
            FULL_NAME: [MessageHandler(text_only, full_name)],
            CONTACT: [MessageHandler(text_only, contact)],
            EVENT_NAME: [MessageHandler(text_only, event_name)],
            DEPARTMENT: [MessageHandler(text_only, department)],
            DATE: [MessageHandler(text_only, date)],
            TIME: [MessageHandler(text_only, time)],
            VENUE: [MessageHandler(text_only, venue)],
            DESCRIPTION: [MessageHandler(text_only, description)],
            LAPTOP: [CallbackQueryHandler(laptop, pattern="^laptop_")],
            CONFIRM: [CallbackQueryHandler(confirm, pattern="^confirm_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(finish_filter, cancel),
            MessageHandler(new_request_filter, start),
        ],
    )
