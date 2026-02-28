import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
WEBAPP_URL = "https://avto-test-uz-three.vercel.app"
ADMIN_URL  = "https://t.me/kamron201"

# Stikerlar (Telegram standart stiker ID lari)
STICKER_WELCOME = "CAACAgIAAxkBAAIBsWd5bJ9VHpY6Y2BqGNqvE_l2fLlCAAIDAAP3AaQR2pGqAAHxHi4XNQQ"
STICKER_TEST    = "CAACAgIAAxkBAAIBs2d5bKhidvOlhYnHkixHqvJE7IKKAAIGAAPSQCQTMKCd-bRs_ZQNBQ"
STICKER_PREMIUM = "CAACAgIAAxkBAAIBtWd5bLjxKb7UJHK7hPlRGO21BFHhAAIKAAPSQCQT2nGe5GkDZGQNBQ"
STICKER_STATS   = "CAACAgIAAxkBAAIBt2d5bME1zT_f6V5v3cMR_3q1WL-ZAAINAAPOQCQT7LNbO0YGAAHMDZINBQ"

# ===================== DATABASE =====================
def init_db():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS test_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        started_at TEXT
    )""")
    conn.commit()
    conn.close()

def save_user(user_id, username, full_name):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, username, full_name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def save_test(user_id):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO test_sessions (user_id, started_at) VALUES (?, ?)",
        (user_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_tests = c.execute("SELECT COUNT(*) FROM test_sessions").fetchone()[0]
    today = datetime.now().date().isoformat()
    today_users = c.execute(
        "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (today + "%",)
    ).fetchone()[0]
    today_tests = c.execute(
        "SELECT COUNT(*) FROM test_sessions WHERE started_at LIKE ?", (today + "%",)
    ).fetchone()[0]
    conn.close()
    return total_users, total_tests, today_users, today_tests

# ===================== MENU =====================
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi"), KeyboardButton("⭐ Premium")],
        [KeyboardButton("📊 Statistika"),      KeyboardButton("ℹ️ Yordam")],
    ], resize_keyboard=True)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")

    # Stiker yuborish
    try:
        await update.message.reply_sticker(STICKER_WELCOME)
    except:
        pass

    text = (
        "👋 *Assalomu alaykum, " + user.first_name + "!*\n\n"
        "🚗 *AvtoTest.Uz* ga xush kelibsiz!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *Bu bot nimaga kerak?*\n\n"
        "✅ Haydovchilik imtihoniga tayyorlanish\n"
        "📝 1000+ ta test savoli\n"
        "🏆 Real GAI imtihoni muhiti\n"
        "📊 Natijalaringizni kuzatish\n"
        "⭐ Premium - cheksiz imkoniyatlar\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 Quyidagi menyudan boshlang!"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    # ── TEST BOSHLASH ──
    if text == "🚗 Testni boshlash":
        save_test(user.id)
        try:
            await update.message.reply_sticker(STICKER_TEST)
        except:
            pass

        info_text = (
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
            "👇 Testni boshlash uchun tugmani bosing:"
        )
        await update.message.reply_text(
            info_text,
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
            "📖  YHQ kitob - barcha 29 bob\n"
            "🔍  Har xatoga batafsil izoh\n"
            "🏆  Reyting tizimida ustunlik\n"
            "📊  Chuqur statistika va tahlil\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 *Narxlar:*\n\n"
            "📅  1 Hafta - *15 000 so'm*\n"
            "🔥  1 Oy    - *49 000 so'm*\n"
            "💎  1 Yil   - *149 000 so'm*\n"
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
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ AvtoTest.Uz Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
