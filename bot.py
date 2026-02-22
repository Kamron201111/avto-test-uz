import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
WEBAPP_URL = "https://avto-test-uz-three.vercel.app"
QOIDALAR_URL = "https://lex.uz/acts/-2850459"

# Admin Telegram ID — siz o'zingiznikini qo'ying
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1234567890"))

# To'lov ma'lumotlari
CLICK_NUMBER = os.environ.get("CLICK_NUMBER", "9901234567")   # Click raqamingiz
PAYME_NUMBER = os.environ.get("PAYME_NUMBER", "9901234567")   # Payme raqamingiz
CARD_NUMBER  = os.environ.get("CARD_NUMBER",  "8600 0000 0000 0000")  # Karta raqamingiz
CARD_OWNER   = os.environ.get("CARD_OWNER",   "Valiyev Kamron")

# Narxlar (so'm)
PRICES = {
    "1_hafta":  {"label": "1 hafta",  "price": 15000,  "days": 7},
    "1_oy":     {"label": "1 oy",     "price": 49000,  "days": 30},
    "3_oy":     {"label": "3 oy",     "price": 120000, "days": 90},
}

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            plan TEXT,
            activated_at TEXT,
            expires_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            plan TEXT,
            price INTEGER,
            requested_at TEXT,
            status TEXT DEFAULT 'pending'
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
    total_users   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_tests   = c.execute("SELECT COUNT(*) FROM test_sessions").fetchone()[0]
    total_premium = c.execute("SELECT COUNT(*) FROM premium_users WHERE expires_at > ?",
                              (datetime.now().isoformat(),)).fetchone()[0]
    today = datetime.now().date().isoformat()
    today_tests   = c.execute("SELECT COUNT(*) FROM test_sessions WHERE started_at LIKE ?",
                              (f"{today}%",)).fetchone()[0]
    conn.close()
    return total_users, total_tests, today_tests, total_premium

def is_premium(user_id):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    row = c.execute("SELECT expires_at FROM premium_users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return False, None
    expires = datetime.fromisoformat(row[0])
    if expires > datetime.now():
        return True, expires
    return False, expires

def activate_premium(user_id, username, full_name, plan_key):
    days = PRICES[plan_key]["days"]
    now = datetime.now()
    expires = now + timedelta(days=days)
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO premium_users (user_id, username, full_name, plan, activated_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, full_name, plan_key, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return expires

def generate_premium_code(plan_key):
    """Sayt uchun maxsus premium kod yaratish"""
    import random, string
    days = PRICES[plan_key]["days"]
    chars = string.ascii_uppercase + string.digits
    uid = ''.join(random.choices(chars, k=4))
    return f"PREM-{uid}-{days}"

def save_payment_request(user_id, username, full_name, plan_key, price):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO payment_requests (user_id, username, full_name, plan, price, requested_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    """, (user_id, username, full_name, plan_key, price, datetime.now().isoformat()))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_pending_requests():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    rows = c.execute("""
        SELECT id, user_id, username, full_name, plan, price, requested_at
        FROM payment_requests WHERE status = 'pending'
        ORDER BY requested_at DESC
    """).fetchall()
    conn.close()
    return rows

def update_request_status(req_id, status):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("UPDATE payment_requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()

# =================== KEYBOARDS ===================
def main_menu(user_id=None):
    premium_ok, _ = is_premium(user_id) if user_id else (False, None)
    premium_btn = "⭐ Premium (Faol)" if premium_ok else "⭐ Premium olish"
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
        [KeyboardButton(premium_btn)],
        [KeyboardButton("📊 Statistika"), KeyboardButton("ℹ️ Yordam")],
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
        [KeyboardButton("⭐ Premium olish")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("ℹ️ Yordam")],
        [KeyboardButton("🔑 Admin panel")],
    ], resize_keyboard=True)

# =================== HANDLERS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or "", user.full_name or "")
    is_admin = user.id == ADMIN_ID

    text = (
        f"👋 Assalomu alaykum, *{user.first_name}*!\n\n"
        "🚗 *AvtoTest.Uz* botiga xush kelibsiz!\n\n"
        "Bu bot orqali siz:\n"
        "✅ Haydovchilik testlarini topshirishingiz\n"
        "📚 Yo'l harakati qoidalarini o'rganishingiz\n"
        "⭐ Premium obuna orqali cheksiz imkoniyatlardan foydalanishingiz mumkin\n\n"
        "Quyidagi menyudan foydalaning 👇"
    )
    kb = admin_menu() if is_admin else main_menu(user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    is_admin = user.id == ADMIN_ID

    # ===================== TEST =====================
    if text == "🚗 Testni boshlash":
        save_test_start(user.id)
        ok, expires = is_premium(user.id)

        if ok:
            msg = (
                "🎯 *Premium foydalanuvchi!*\n\n"
                f"⭐ Obunangiz: *{expires.strftime('%d.%m.%Y')}* gacha\n\n"
                "✅ Cheksiz test topshirish imkoniyati faol\n"
                "📝 Testni boshlash uchun tugmani bosing 👇"
            )
        else:
            msg = (
                "🎯 Test boshlashga tayyormisiz?\n\n"
                "📌 Test 20 ta savoldan iborat\n"
                "⏱ Har bir savolga vaqt belgilangan\n"
                "✅ 70% dan yuqori ball — o'tdi!\n\n"
                "💡 *Premium* obuna bilan cheksiz test va xatolar tahlilidan foydalaning!\n\n"
                "Quyidagi tugmani bosib testni boshlang 👇"
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Testni ochish", url=WEBAPP_URL)]
        ])
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    # ===================== QOIDALAR =====================
    elif text == "📚 Qoidalar kitobi":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Qoidalarni o'qish", url=QOIDALAR_URL)]
        ])
        await update.message.reply_text(
            "📚 *Yo'l harakati qoidalari*\n\n"
            "O'zbekiston Respublikasining yo'l harakati qoidalari bilan "
            "tanishib chiqing!\n\n"
            "👇 Tugmani bosib o'qing:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    # ===================== PREMIUM =====================
    elif text in ["⭐ Premium olish", "⭐ Premium (Faol)"]:
        ok, expires = is_premium(user.id)

        if ok:
            await update.message.reply_text(
                f"⭐ *Sizda Premium faol!*\n\n"
                f"📅 Muddati: *{expires.strftime('%d.%m.%Y %H:%M')}* gacha\n\n"
                "✅ Cheksiz test\n"
                "✅ Xatolar tahlili\n"
                "✅ Real imtihon simulyatori\n\n"
                "Yangilash uchun ham quyidagi tugmani bosing 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Obunani yangilash", callback_data="premium_plans")]
                ])
            )
        else:
            await update.message.reply_text(
                "⭐ *Premium obuna*\n\n"
                "Premium bilan nimalar ochiladi:\n\n"
                "♾ *Cheksiz test* — kunlik limit yo'q\n"
                "🔍 *Xatolar tahlili* — har bir xatongiz tushuntiriladi\n"
                "🏛 *Real simulyator* — GAI imtihoni muhiti\n\n"
                "Paketni tanlang 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📦 Paketni tanlash", callback_data="premium_plans")]
                ])
            )

    # ===================== STATISTIKA =====================
    elif text == "📊 Statistika":
        total_users, total_tests, today_tests, total_premium = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            f"👥 Jami foydalanuvchilar: *{total_users}* ta\n"
            f"⭐ Premium foydalanuvchilar: *{total_premium}* ta\n"
            f"📝 Jami test boshlangan: *{total_tests}* marta\n"
            f"📅 Bugun test boshlangan: *{today_tests}* marta\n\n"
            f"🕐 Yangilangan: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )

    # ===================== YORDAM =====================
    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "ℹ️ *Yordam*\n\n"
            "🚗 *Testni boshlash* — Haydovchilik testini topshirish\n"
            "📚 *Qoidalar kitobi* — Yo'l harakati qoidalari\n"
            "⭐ *Premium* — Cheksiz imkoniyatlar\n"
            "📊 *Statistika* — Umumiy statistika\n\n"
            "❓ Muammo bo'lsa: @RuldaTestBot ga yozing",
            parse_mode="Markdown"
        )

    # ===================== ADMIN PANEL =====================
    elif text == "🔑 Admin panel" and is_admin:
        pending = get_pending_requests()
        if not pending:
            await update.message.reply_text(
                "🔑 *Admin panel*\n\n"
                "✅ Hozircha kutilayotgan to'lovlar yo'q.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Barcha so'rovlar", callback_data="admin_all")]
                ])
            )
        else:
            await update.message.reply_text(
                f"🔑 *Admin panel*\n\n"
                f"⏳ Kutilayotgan to'lovlar: *{len(pending)}* ta\n\n"
                "Tasdiqlash uchun quyidan tanlang 👇",
                parse_mode="Markdown"
            )
            for req in pending[:10]:
                req_id, uid, uname, fname, plan, price, req_at = req
                plan_label = PRICES.get(plan, {}).get("label", plan)
                await update.message.reply_text(
                    f"👤 *{fname}* (@{uname or 'noma\'lum'})\n"
                    f"🆔 ID: `{uid}`\n"
                    f"📦 Paket: *{plan_label}*\n"
                    f"💰 Summa: *{price:,} so'm*\n"
                    f"🕐 Vaqt: {req_at[:16]}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{req_id}_{uid}__{plan}"),
                            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{req_id}_{uid}")
                        ]
                    ])
                )

    else:
        await update.message.reply_text(
            "Iltimos, quyidagi menyudan tanlang 👇",
            reply_markup=main_menu(user.id)
        )

# =================== CALLBACK HANDLERS ===================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    # ---- Premium paketlar ----
    if data == "premium_plans":
        buttons = []
        for key, val in PRICES.items():
            buttons.append([InlineKeyboardButton(
                f"📦 {val['label']} — {val['price']:,} so'm",
                callback_data=f"buy_{key}"
            )])
        await query.message.reply_text(
            "📦 *Paketni tanlang:*\n\n"
            "🗓 *1 hafta* — 15,000 so'm\n"
            "🗓 *1 oy* — 49,000 so'm\n"
            "🗓 *3 oy* — 120,000 so'm\n\n"
            "✅ To'lovdan so'ng 5-15 daqiqa ichida faollashtiriladi",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # ---- Paket tanlandi ----
    elif data.startswith("buy_"):
        plan_key = data.replace("buy_", "")
        if plan_key not in PRICES:
            return
        plan = PRICES[plan_key]
        req_id = save_payment_request(
            user.id, user.username or "", user.full_name or "",
            plan_key, plan["price"]
        )
        await query.message.reply_text(
            f"💳 *To'lov ma'lumotlari*\n\n"
            f"📦 Paket: *{plan['label']}*\n"
            f"💰 Summa: *{plan['price']:,} so'm*\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💳 *Karta:* `{CARD_NUMBER}`\n"
            f"👤 *Egasi:* {CARD_OWNER}\n\n"
            f"📱 *Click:* `{CLICK_NUMBER}`\n"
            f"📱 *Payme:* `{PAYME_NUMBER}`\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ *Muhim:* To'lov cheki yoki skrinshot yuboring!\n"
            f"🔢 So'rov raqami: *#{req_id}*\n\n"
            f"✅ Admin 5-15 daqiqa ichida faollashtiradi",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Chek yuborish", callback_data=f"send_receipt_{req_id}")]
            ])
        )
        # Adminga xabar
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 *Yangi to'lov so'rovi!*\n\n"
            f"👤 *{user.full_name}* (@{user.username or 'noma\'lum'})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📦 Paket: *{plan['label']}*\n"
            f"💰 Summa: *{plan['price']:,} so'm*\n"
            f"🔢 So'rov: *#{req_id}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{req_id}_{user.id}__{plan_key}"),
                    InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{req_id}_{user.id}")
                ]
            ])
        )

    # ---- Chek yuborish ----
    elif data.startswith("send_receipt_"):
        await query.message.reply_text(
            "📤 *Chek yuboring*\n\n"
            "To'lov skrinshotini yoki chekini shu yerga yuboring.\n"
            "Admin ko'rib chiqib, obunangizni faollashtiradi ✅",
            parse_mode="Markdown"
        )

    # ---- Admin: Tasdiqlash ----
    elif data.startswith("approve_"):
        if user.id != ADMIN_ID:
            await query.answer("Sizda huquq yo'q!", show_alert=True)
            return
        # format: approve_{req_id}_{user_id}__{plan_key}
        without_prefix = data[len("approve_"):]  # req_id_{user_id}__{plan_key}
        double_idx = without_prefix.index("__")
        before = without_prefix[:double_idx]   # req_id_{user_id}
        plan_key = without_prefix[double_idx+2:]  # plan_key (1_hafta, 1_oy, 3_oy)
        id_parts = before.split("_")
        req_id = int(id_parts[0])
        target_user_id = int(id_parts[1])

        # Foydalanuvchi ma'lumotlarini olish
        conn = sqlite3.connect("stats.db")
        c = conn.cursor()
        row = c.execute("SELECT username, full_name FROM payment_requests WHERE id = ?", (req_id,)).fetchone()
        conn.close()
        uname, fname = (row[0], row[1]) if row else ("", "")

        expires = activate_premium(target_user_id, uname, fname, plan_key)
        update_request_status(req_id, "approved")
        plan_label = PRICES.get(plan_key, {}).get("label", plan_key)

        # Sayt uchun premium kod yaratish
        premium_code = generate_premium_code(plan_key)

        # Foydalanuvchiga xabar
        try:
            await context.bot.send_message(
                target_user_id,
                f"🎉 *Tabriklaymiz! Premium tasdiqlandi!*\n\n"
                f"📦 Paket: *{plan_label}*\n"
                f"📅 Muddati: *{expires.strftime('%d.%m.%Y')}* gacha\n\n"
                f"🔑 *Sayt uchun premium kod:*\n"
                f"`{premium_code}`\n\n"
                f"📌 *Qanday ishlatish:*\n"
                f"1️⃣ Saytga kiring\n"
                f"2️⃣ Dashboard da ⭐ Premium tugmasini bosing\n"
                f"3️⃣ Yuqoridagi kodni kiriting\n"
                f"4️⃣ Faollashtirish bosing\n\n"
                f"✅ Cheksiz test\n"
                f"✅ Xatolar tahlili\n"
                f"✅ Real imtihon simulyatori\n\n"
                f"Testni boshlang! 🚗",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Foydalanuvchiga xabar yuborishda xato: {e}")

        await query.edit_message_text(
            f"✅ *Tasdiqlandi!*\n\n"
            f"👤 {fname} (@{uname})\n"
            f"📦 {plan_label} — {expires.strftime('%d.%m.%Y')} gacha",
            parse_mode="Markdown"
        )

    # ---- Admin: Rad etish ----
    elif data.startswith("reject_"):
        if user.id != ADMIN_ID:
            await query.answer("Sizda huquq yo'q!", show_alert=True)
            return
        parts = data.split("_")
        req_id = int(parts[1])
        target_user_id = int(parts[2])
        update_request_status(req_id, "rejected")

        try:
            await context.bot.send_message(
                target_user_id,
                "❌ *To'lovingiz tasdiqlanmadi.*\n\n"
                "Muammo bo'lsa admin bilan bog'laning yoki qaytadan urinib ko'ring.",
                parse_mode="Markdown"
            )
        except:
            pass

        await query.edit_message_text("❌ Rad etildi.")

# =================== RECEIPT PHOTO =====================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    caption = update.message.caption or ""

    # Adminga chekni yuborish
    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=(
            f"📤 *Chek keldi!*\n\n"
            f"👤 *{user.full_name}* (@{user.username or 'noma\'lum'})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📝 Izoh: {caption or 'yo\'q'}\n\n"
            f"Yuqoridagi so'rovni tasdiqlang ✅"
        ),
        parse_mode="Markdown"
    )
    await update.message.reply_text(
        "✅ Chekingiz adminga yuborildi!\n"
        "5-15 daqiqa ichida obunangiz faollashtiriladi."
    )

# =================== MAIN ===================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
