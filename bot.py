import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# load_dotenv(override=False) — Railway Variables ustunlik qiladi, .env faqat local uchun
load_dotenv(override=False)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://avto-test-uz-three.vercel.app")
ADMIN_URL  = "https://t.me/kamron201"

# ✅ Majburiy obuna kanali
CHANNEL_USERNAME = "@premium_milliy"
CHANNEL_URL      = "https://t.me/premium_milliy"

# Supabase — Railway Variables dan olinadi
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

logger.info(f"SUPABASE_URL: {SUPABASE_URL[:30] if SUPABASE_URL else 'EMPTY'}")
logger.info(f"SUPABASE_KEY: {SUPABASE_KEY[:20] if SUPABASE_KEY else 'EMPTY'}...")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL yoki SUPABASE_KEY Railway Variables da yo'q!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stikerlar
STICKER_WELCOME = "CAACAgIAAxkBAAIBsWd5bJ9VHpY6Y2BqGNqvE_l2fLlCAAIDAAP3AaQR2pGqAAHxHi4XNQQ"
STICKER_TEST    = "CAACAgIAAxkBAAIBs2d5bKhidvOlhYnHkixHqvJE7IKKAAIGAAPSQCQTMKCd-bRs_ZQNBQ"
STICKER_PREMIUM = "CAACAgIAAxkBAAIBtWd5bLjxKb7UJHK7hPlRGO21BFHhAAIKAAPSQCQT2nGe5GkDZGQNBQ"
STICKER_STATS   = "CAACAgIAAxkBAAIBt2d5bME1zT_f6V5v3cMR_3q1WL-ZAAINAAPOQCQT7LNbO0YGAAHMDZINBQ"

# ===================== SUPABASE DATABASE =====================
# Supabase da bu 2 ta jadval kerak (bir marta yaratiladi):
#
# CREATE TABLE IF NOT EXISTS bot_users (
#     user_id BIGINT PRIMARY KEY,
#     username TEXT,
#     full_name TEXT,
#     joined_at TIMESTAMPTZ DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS bot_test_sessions (
#     id BIGSERIAL PRIMARY KEY,
#     user_id BIGINT,
#     started_at TIMESTAMPTZ DEFAULT NOW()
# );

def save_user(user_id: int, username: str, full_name: str):
    """Yangi foydalanuvchini saqlash — agar avval yo'q bo'lsa"""
    try:
        # upsert ishlatmaymiz — faqat yangi bo'lsa qo'shamiz
        existing = supabase.table("bot_users").select("user_id").eq("user_id", user_id).execute()
        if not existing.data:
            supabase.table("bot_users").insert({
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "joined_at": datetime.utcnow().isoformat()
            }).execute()
    except Exception as e:
        logger.error(f"save_user xatosi: {e}")

def save_test(user_id: int):
    """Test sessiyasini saqlash"""
    try:
        supabase.table("bot_test_sessions").insert({
            "user_id": user_id,
            "started_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"save_test xatosi: {e}")

def get_stats():
    """Barcha statistikani olish"""
    try:
        # Jami foydalanuvchilar
        total_users_res = supabase.table("bot_users").select("user_id", count="exact").execute()
        total_users = total_users_res.count or 0

        # Jami testlar
        total_tests_res = supabase.table("bot_test_sessions").select("id", count="exact").execute()
        total_tests = total_tests_res.count or 0

        # Bugungi sana (UTC)
        today_str = datetime.utcnow().date().isoformat()
        today_start = today_str + "T00:00:00"
        today_end   = today_str + "T23:59:59"

        # Bugungi yangi foydalanuvchilar
        today_users_res = supabase.table("bot_users") \
            .select("user_id", count="exact") \
            .gte("joined_at", today_start) \
            .lte("joined_at", today_end) \
            .execute()
        today_users = today_users_res.count or 0

        # Bugungi testlar
        today_tests_res = supabase.table("bot_test_sessions") \
            .select("id", count="exact") \
            .gte("started_at", today_start) \
            .lte("started_at", today_end) \
            .execute()
        today_tests = today_tests_res.count or 0

        return total_users, total_tests, today_users, today_tests

    except Exception as e:
        logger.error(f"get_stats xatosi: {e}")
        return 0, 0, 0, 0

# ===================== KANAL TEKSHIRUVI =====================
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"Kanal tekshirishda xato: {e}")
        return True  # xato bo'lsa o'tkazib yuborish

async def send_subscribe_prompt(update: Update):
    text = (
        "🔐 *Botdan foydalanish uchun kanalga obuna bo'ling!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 *Premium Milliy* — rasmiy kanalimiz\n\n"
        "Kanalga obuna bo'lsangiz:\n\n"
        "🎯 Bot yangiliklari va imkoniyatlardan birinchi bo'lib xabardor bo'lasiz\n"
        "💡 Haydovchilik bo'yicha foydali maslahatlar olasiz\n"
        "📋 Imtihon sirlari va qo'llanmalardan foydalanasiz\n"
        "🎁 Maxsus aksiya va chegirmalardan bahramand bo'lasiz\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 *1-qadam:* Kanalga o'ting va obuna bo'ling\n"
        "👇 *2-qadam:* «✅ Obuna bo'ldim» tugmasini bosing"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga o'tish →", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Obuna bo'ldim — Tekshirish", callback_data="check_sub")],
    ])
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

# ===================== MENU =====================
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi"), KeyboardButton("⭐ Premium")],
        [KeyboardButton("📊 Statistika"),      KeyboardButton("ℹ️ Yordam")],
    ], resize_keyboard=True)

async def send_welcome(chat_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=STICKER_WELCOME)
    except:
        pass

    text = (
        "✅ *Tabriklaymiz! Obuna tasdiqlandi.*\n\n"
        "👋 Xush kelibsiz, *" + first_name + "*!\n\n"
        "🚗 [RuldaTest.uz](" + WEBAPP_URL + ") ga xush kelibsiz!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *Bu bot nimaga kerak?*\n\n"
        "✅ Haydovchilik imtihoniga tayyorlanish\n"
        "📝 1000+ ta test savoli\n"
        "🏆 Real GAI imtihoni muhiti\n"
        "📊 Natijalaringizni kuzatish\n"
        "⭐ Premium — cheksiz imkoniyatlar\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 Quyidagi menyudan boshlang!"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")

    if not await is_subscribed(user.id, context):
        await send_subscribe_prompt(update)
        return

    await send_welcome(user.id, user.first_name, context)


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if await is_subscribed(user.id, context):
        try:
            await query.message.delete()
        except:
            pass
        save_user(user.id, user.username or "", user.full_name or "")
        await send_welcome(user.id, user.first_name, context)
    else:
        await query.answer(
            "❌ Siz hali kanalga obuna bo'lmagansiz!\n\n"
            "Avval «📢 Kanalga o'tish» tugmasini bosing va obuna bo'ling.",
            show_alert=True
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if not await is_subscribed(user.id, context):
        await send_subscribe_prompt(update)
        return

    # ── TEST BOSHLASH ──
    if text == "🚗 Testni boshlash":
        save_test(user.id)
        try:
            await update.message.reply_sticker(STICKER_TEST)
        except:
            pass

        await update.message.reply_text(
            "🚗 *Test haqida ma'lumot*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Savollar soni:* 20 ta\n"
            "⏱ *Vaqt:* Cheklanmagan\n"
            "✅ *O'tish bali:* 85% va undan yuqori\n"
            "📖 *Mavzular:*\n"
            "   • Yo'l harakati qoidalari\n"
            "   • Yo'l belgilari va chiziqlar\n"
            "   • Haydovchi va yo'lovchi xavfsizligi\n"
            "   • Texnik holat va jarimalar\n"
            "   • Birinchi tibbiy yordam\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🆓 *Bepul:* Kuniga 20 ta test\n"
            "👑 *Premium:* Cheksiz test + ko'proq!\n\n"
            "👇 Testni boshlash uchun tugmani bosing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Testni boshlash!", web_app=__import__("telegram").WebAppInfo(url=WEBAPP_URL))
            ]])
        )

    # ── QOIDALAR KITOBI ──
    elif text == "📚 Qoidalar kitobi":
        await update.message.reply_text(
            "📚 *Yo'l harakati qoidalari*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "O'zbekiston Respublikasining\n"
            "rasmiy YHQ kitobi!\n\n"
            "📖 *Mavzular:*\n"
            "• Umumiy qoidalar\n"
            "• Yo'l belgilari (29 bob)\n"
            "• Harakatlanish tartibi\n"
            "• Jarimalar va javobgarlik\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 O'qish uchun tugmani bosing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 Qoidalarni o'qish", url="https://lex.uz/acts/-2850459")
            ]])
        )

    # ── PREMIUM ──
    elif text == "⭐ Premium":
        try:
            await update.message.reply_sticker(STICKER_PREMIUM)
        except:
            pass

        await update.message.reply_text(
            "⭐ *Premium Obuna*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👑 *Premium bilan nimalar ochiladi:*\n\n"
            "♾️  Cheksiz kunlik testlar\n"
            "🎬  20 ta video dars\n"
            "📖  YHQ kitob — barcha 29 bob\n"
            "🔍  Har xatoga batafsil izoh\n"
            "🏆  Reyting tizimida ustunlik\n"
            "📊  Chuqur statistika va tahlil\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 *Narxlar:*\n\n"
            "📅  1 Hafta  —  *15 000 so'm*\n"
            "🔥  1 Oy     —  *49 000 so'm*\n"
            "💎  1 Yil    —  *149 000 so'm*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 Saytda Premium oling:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Premium olish", web_app=__import__("telegram").WebAppInfo(url=WEBAPP_URL))
            ]])
        )

    # ── STATISTIKA ──
    elif text == "📊 Statistika":
        try:
            await update.message.reply_sticker(STICKER_STATS)
        except:
            pass

        total_users, total_tests, today_users, today_tests = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👥 *Jami foydalanuvchilar:* " + str(total_users) + " ta\n"
            "📝 *Jami testlar:* " + str(total_tests) + " ta\n\n"
            "📅 *Bugun:*\n"
            "   🆕 Yangi foydalanuvchilar: " + str(today_users) + " ta\n"
            "   🧪 Testlar boshlandi: " + str(today_tests) + " ta\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🕐 " + datetime.now().strftime("%d.%m.%Y %H:%M"),
            parse_mode="Markdown"
        )

    # ── YORDAM ──
    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "ℹ️ *Yordam va qo'llanma*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚗 *Testni boshlash*\n"
            "   GAI imtihon testini topshirish\n\n"
            "📚 *Qoidalar kitobi*\n"
            "   Rasmiy YHQ ni o'qish\n\n"
            "⭐ *Premium*\n"
            "   Cheksiz test va qo'shimcha imkoniyatlar\n\n"
            "📊 *Statistika*\n"
            "   Bot umumiy statistikasi\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "❓ *Muammo yoki savol bo'lsa:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✍️ Adminga yozish", url=ADMIN_URL)
            ]])
        )

    else:
        await update.message.reply_text(
            "👇 Pastdagi menyudan foydalaning:",
            reply_markup=main_menu()
        )


# ===================== MAIN =====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ AvtoTest.Uz Bot ishga tushdi! (Supabase storage)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
