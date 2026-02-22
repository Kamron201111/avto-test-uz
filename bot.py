import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
WEBAPP_URL = "https://avto-test-uz-three.vercel.app"
QOIDALAR_URL = "https://lex.uz/acts/-2850459"

# =================== DATABASE ===================
def init_db():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            started_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id, username, full_name):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, full_name, datetime.now().isoformat()))
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
    today_tests = c.execute(
        "SELECT COUNT(*) FROM test_sessions WHERE started_at LIKE ?", (f"{today}%",)
    ).fetchone()[0]
    conn.close()
    return total_users, total_tests, today_tests

# =================== KEYBOARDS ===================
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("ℹ️ Yordam")]
    ], resize_keyboard=True)

# =================== HANDLERS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")
    
    text = (
        f"👋 Assalomu alaykum, *{user.first_name}*!\n\n"
        "🚗 *AvtoTest.Uz* botiga xush kelibsiz!\n\n"
        "Bu bot orqali siz:\n"
        "✅ Haydovchilik testlarini topshirishingiz\n"
        "📚 Yo'l harakati qoidalarini o'rganishingiz\n"
        "📊 Statistikani ko'rishingiz mumkin\n\n"
        "Quyidagi menyudan foydalaning 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🚗 Testni boshlash":
        save_test_start(user.id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📝 Testni ochish",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ])
        await update.message.reply_text(
            "🎯 Test boshlashga tayyormisiz?\n\n"
            "📌 Test 20 ta savoldan iborat\n"
            "⏱ Har bir savolga vaqt belgilangan\n"
            "✅ 70% dan yuqori ball — o'tdi!\n\n"
            "Quyidagi tugmani bosib testni boshlang 👇",
            reply_markup=keyboard
        )

    elif text == "📚 Qoidalar kitobi":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Qoidalarni o'qish", url=QOIDALAR_URL)]
        ])
        await update.message.reply_text(
            "📚 *Yo'l harakati qoidalari*\n\n"
            "O'zbekiston Respublikasining yo'l harakati qoidalari bilan "
            "tanishib chiqing. Bu sizga testda yuqori ball olishga yordam beradi!\n\n"
            "👇 Tugmani bosib o'qing:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    elif text == "📊 Statistika":
        total_users, total_tests, today_tests = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            f"👥 Jami foydalanuvchilar: *{total_users}* ta\n"
            f"📝 Jami test boshlangan: *{total_tests}* marta\n"
            f"📅 Bugun test boshlangan: *{today_tests}* marta\n\n"
            f"🕐 Yangilangan: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )

    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "ℹ️ *Yordam*\n\n"
            "🚗 *Testni boshlash* — Haydovchilik testini topshirish\n"
            "📚 *Qoidalar kitobi* — Yo'l harakati qoidalari\n"
            "📊 *Statistika* — Umumiy statistika\n\n"
            "❓ Muammo bo'lsa: @admin ga yozing",
            parse_mode="Markdown"
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
