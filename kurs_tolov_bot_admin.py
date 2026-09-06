"""
Kurs sotuvi uchun to'liq avtomatlashtirilgan Telegram bot (ADMIN TASDIQLASH BILAN).

Ishlash tartibi:
1. Foydalanuvchi botga /start bosadi.
2. Bot xush kelibsiz xabarini, kurs taqdimoti rasmini va to'lov uchun
   karta raqamini yuboradi, chek (skrinshot) tashlashni so'raydi.
3. Foydalanuvchi to'lov chekining skrinshotini yuboradi.
   - Agar bu foydalanuvchi ILGARI ALLAQACHON havola olgan bo'lsa, bot
     "Siz avval to'lov qilgansiz va havola olgansiz" deb javob beradi
     va chekni adminga umuman yubormaydi.
4. Aks holda, bot bu skrinshotni ADMINGA (sizga) "✅ Tasdiqlash" /
   "❌ Rad etish" tugmalari bilan yuboradi.
5. Admin "✅ Tasdiqlash" tugmasini bossa: bot 30 soniya kutadi, so'ng
   yopiq "darslar" kanali uchun BIR MARTALIK taklif havolasini yaratadi
   va foydalanuvchiga yuboradi, so'ng bu foydalanuvchini "allaqachon
   xizmat ko'rsatilgan" deb belgilab qo'yadi (endi qayta link ololmaydi).
   Admin "❌ Rad etish" tugmasini bossa: foydalanuvchiga to'g'ri chek
   qayta yuborish so'raladi (bu holatda foydalanuvchi keyinroq yana
   chek yuborishi mumkin, chunki hali link berilmagan).

O'rnatish:
    pip install python-telegram-bot --break-system-packages

TO'LDIRISH SHART BO'LGAN JOYLAR (Railway > Variables bo'limida, kodda emas!):
    BOT_TOKEN - @BotFather dan olingan token
    ADMIN_ID  - sizning shaxsiy Telegram ID raqamingiz (@userinfobot dan)

IMAGE_PATH sifatida shu skriptning yonidagi "kurs_taqdimoti.jpg" faylini
qoldiring (repoga allaqachon yuklangan).

approved_users.json - bot papkasida avtomatik yaratiladigan fayl, allaqachon
link olgan foydalanuvchilar ro'yxatini saqlaydi (bot qayta ishga tushsa ham
yo'qolmasligi uchun).
"""

import asyncio
import json
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
CHANNEL_ID = -1004499270578           # darslar bo'ladigan yopiq kanal ID
CARD_NUMBER = "5614 6846 0443 8166"   # Uzcard
WAIT_SECONDS = 30

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(SCRIPT_DIR, "kurs_taqdimoti.jpg")
APPROVED_USERS_FILE = os.path.join(SCRIPT_DIR, "approved_users.json")

# user_id -> {"chat_id": ..., "username": ...} - tasdiq kutayotgan foydalanuvchilar
pending_users: dict[int, dict] = {}


def load_approved_users() -> set[int]:
    if os.path.exists(APPROVED_USERS_FILE):
        try:
            with open(APPROVED_USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error("approved_users.json o'qishda xatolik: %s", e)
    return set()


def save_approved_users(users: set[int]) -> None:
    try:
        with open(APPROVED_USERS_FILE, "w") as f:
            json.dump(list(users), f)
    except Exception as e:
        logging.error("approved_users.json yozishda xatolik: %s", e)


# Bot ishga tushganda avvalgi ro'yxatni yuklaydi
approved_users: set[int] = load_approved_users()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    caption = (
        "Kursga xush kelibsiz! 🎓\n\n"
        "Darslar bo'ladigan kanalga o'tish uchun to'lovni amalga oshiring "
        "va to'lov chekini skrinshot qilib shu botga yuboring.\n\n"
        f"💳 To'lov uchun karta raqami (Uzcard):\n"
        f"`{CARD_NUMBER}`\n\n"
        "To'lovni amalga oshirgach, chek skrinshotini shu yerga rasm "
        "sifatida yuboring 👇"
    )

    try:
        with open(IMAGE_PATH, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode="Markdown",
            )
    except FileNotFoundError:
        logging.error("Rasm topilmadi: %s", IMAGE_PATH)
        await update.message.reply_text(caption, parse_mode="Markdown")


async def handle_payment_screenshot(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user

    # Bu foydalanuvchi ILGARI ALLAQACHON havola olgan bo'lsa - qayta bermaymiz
    if user.id in approved_users:
        await update.message.reply_text(
            "Siz avval to'lov qilgansiz va darslar kanaliga havola "
            "olib bo'lgansiz. Har bir foydalanuvchiga faqat bitta "
            "havola beriladi."
        )
        logging.info("Qayta urinish rad etildi: user_id=%s", user.id)
        return

    # Chek allaqachon adminga yuborilib, javob kutilayotgan bo'lsa - qayta
    # yubormaymiz, faqat eslatamiz
    if user.id in pending_users:
        await update.message.reply_text(
            "Sizning oldingi chekingiz hali admin tomonidan ko'rib "
            "chiqilmoqda. Biroz kuting."
        )
        return

    pending_users[user.id] = {
        "chat_id": update.effective_chat.id,
        "username": user.username or user.full_name,
    }

    await update.message.reply_text(
        "Chekingiz qabul qilindi ✅\n"
        "Admin tomonidan tekshirilmoqda, biroz kuting..."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Tasdiqlash", callback_data=f"approve_{user.id}"
                ),
                InlineKeyboardButton(
                    "❌ Rad etish", callback_data=f"reject_{user.id}"
                ),
            ]
        ]
    )

    photo_file_id = update.message.photo[-1].file_id

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_file_id,
        caption=(
            f"Yangi to'lov cheki ⬆️\n"
            f"Foydalanuvchi: @{user.username or '-'} ({user.full_name})\n"
            f"ID: {user.id}"
        ),
        reply_markup=keyboard,
    )

    logging.info("Chek adminga yuborildi: user_id=%s", user.id)


async def handle_admin_decision(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    action, user_id_str = query.data.split("_", 1)
    user_id = int(user_id_str)

    info = pending_users.get(user_id)
    if info is None:
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n⚠️ Bu so'rov allaqachon ko'rib chiqilgan."
        )
        return

    if action == "reject":
        await context.bot.send_message(
            chat_id=info["chat_id"],
            text=(
                "To'lov chekingiz tasdiqlanmadi ❌\n"
                "Iltimos, to'g'ri chekni qayta yuboring."
            ),
        )
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ RAD ETILDI"
        )
        del pending_users[user_id]
        return

    # action == "approve"
    await query.edit_message_caption(
        caption=query.message.caption + "\n\n✅ TASDIQLANDI - havola tayyorlanmoqda..."
    )

    await context.bot.send_message(
        chat_id=info["chat_id"],
        text="To'lovingiz tasdiqlandi! Havola tayyorlanmoqda, biroz kuting...",
    )

    await asyncio.sleep(WAIT_SECONDS)

    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,           # faqat 1 kishi kira oladi
            name=f"invite_{user_id}",
        )

        await context.bot.send_message(
            chat_id=info["chat_id"],
            text=(
                "Darslar kanaliga shaxsiy, bir martalik havolangiz:\n"
                f"{invite_link.invite_link}\n\n"
                "⚠️ Diqqat: bu havola faqat bitta marta ishlaydi, uni "
                "boshqalarga yubormang."
            ),
        )

        # Bu foydalanuvchi endi "xizmat ko'rsatilgan" deb belgilanadi -
        # qayta chek yuborsa ham yangi link olmaydi
        approved_users.add(user_id)
        save_approved_users(approved_users)

        logging.info(
            "Havola yaratildi: user_id=%s link=%s", user_id, invite_link.invite_link
        )

    except Exception as e:
        logging.error("Havola yaratishda xatolik: %s", e)
        await context.bot.send_message(
            chat_id=info["chat_id"],
            text="Kechirasiz, havola yaratishda xatolik yuz berdi. Admin bilan bog'laning.",
        )

    del pending_users[user_id]


async def handle_other_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.message.reply_text(
        "Iltimos, to'lov chekingizni RASM (skrinshot) sifatida yuboring."
    )


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot))
    app.add_handler(CallbackQueryHandler(handle_admin_decision))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other_messages)
    )
    app.run_polling()


if __name__ == "__main__":
    main()
