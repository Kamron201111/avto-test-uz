import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
WEBAPP_URL   = "https://avto-test-uz-three.vercel.app"
QOIDALAR_URL = "https://lex.uz/acts/-2850459"
ADMIN_URL    = "https://t.me/kamron201"

# =================== DATABASE ===================
def init_db():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS test_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, started_at TEXT
    )""")
    conn.commit()
    conn.close()

def save_user(user_id, username, full_name):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)",
              (user_id, username, full_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def save_test_start(user_id):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("INSERT INTO test_sessions (user_id, started_at) VALUES (?, ?)",
              (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_tests = c.execute("SELECT COUNT(*) FROM test_sessions").fetchone()[0]
    today = datetime.now().date().isoformat()
    today_tests = c.execute("SELECT COUNT(*) FROM test_sessions WHERE started_at LIKE ?",
                            (f"{today}%",)).fetchone()[0]
    conn.close()
    return total_users, total_tests, today_tests

# =================== MENU ===================
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
        [KeyboardButton("⭐ Premium haqida")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("ℹ️ Yordam")],
    ], resize_keyboard=True)

# =================== HANDLERS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")
    await update.message.reply_text(
        f"👋 Assalomu alaykum, *{user.first_name}*!\n\n"
        "🚗 *AvtoTest.Uz* botiga xush kelibsiz!\n\n"
        "✅ Kundalik 20 ta bepul test\n"
        "📚 Yo'l harakati qoidalarini o'rganish\n"
        "⭐ Premium — cheksiz test va xatolar tahlili\n\n"
        "👇 Quyidagi menyudan foydalaning:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🚗 Testni boshlash":
        save_test_start(user.id)
        await update.message.reply_text(
            "🎯 *Test boshlashga tayyormisiz?*\n\n"
            "📌 Kuniga 20 ta bepul test\n"
            "⏱ Har bir savolga vaqt belgilangan\n"
            "✅ 85% dan yuqori ball — o'tdi!\n\n"
            "⭐ *Premium* bilan cheksiz test va xatolar tahlili!\n\n"
            "👇 Testni boshlang:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📝 Testni ochish", url=WEBAPP_URL)
            ]])
        )

    elif text == "📚 Qoidalar kitobi":
        await update.message.reply_text(
            "📚 *Yo'l harakati qoidalari*\n\n"
            "O'zbekiston Respublikasining rasmiy yo'l harakati qoidalari!\n\n"
            "👇 Tugmani bosib o'qing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 Qoidalarni o'qish", url=QOIDALAR_URL)
            ]])
        )

    elif text == "⭐ Premium haqida":
        await update.message.reply_text(
            "⭐ *Premium obuna*\n\n"
            "Premium bilan nimalar ochiladi:\n\n"
            "♾ *Cheksiz test* — kunlik limit yo'q\n"
            "🔍 *Xatolar tahlili* — har xatoga tushuntirish\n"
            "🏛 *Real simulyator* — GAI imtihoni muhiti\n"
            "🔔 *Bildirgi* — har xato uchun ogohlantirish\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "💳 *Premium olish:*\n"
            "Saytga kiring va ⭐ Premium tugmasini bosing!\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "👇 Saytda premium oling:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌐 Saytga o'tish", url=WEBAPP_URL)
            ]])
        )

    elif text == "📊 Statistika":
        total_users, total_tests, today_tests = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            f"👥 Jami foydalanuvchilar: *{total_users}* ta\n"
            f"📝 Jami test boshlangan: *{total_tests}* marta\n"
            f"📅 Bugun test boshlangan: *{today_tests}* marta\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )

    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "ℹ️ *Yordam*\n\n"
            "🚗 *Testni boshlash* — Haydovchilik testini topshirish\n"
            "📚 *Qoidalar kitobi* — Yo'l harakati qoidalari\n"
            "⭐ *Premium haqida* — Cheksiz imkoniyatlar\n"
            "📊 *Statistika* — Umumiy statistika\n\n"
            "❓ Muammo bo'lsa adminga yozing 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✍️ Adminga yozish", url=ADMIN_URL)
            ]])
        )

    else:
        await update.message.reply_text(
            "Iltimos, quyidagi menyudan tanlang 👇",
            reply_markup=main_menu()
        )

# =================== MAIN ===================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
