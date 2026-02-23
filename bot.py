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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6498632307"))

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
    c.execute("""CREATE TABLE IF NOT EXISTS premium_users (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        plan TEXT, activated_at TEXT, expires_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    # Default sozlamalar
    defaults = [
        ("card_number", "8600 0000 0000 0000"),
        ("card_owner", "Valiyev Kamron"),
        ("card_type", "Humo / UzCard"),
        ("price_1_hafta", "15000"),
        ("price_1_oy", "49000"),
        ("price_3_oy", "120000"),
        ("click_number", ""),
        ("payme_number", ""),
    ]
    for key, val in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else ""

def set_setting(key, value):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
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
    total_users   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_tests   = c.execute("SELECT COUNT(*) FROM test_sessions").fetchone()[0]
    total_premium = c.execute("SELECT COUNT(*) FROM premium_users WHERE expires_at > ?",
                              (datetime.now().isoformat(),)).fetchone()[0]
    today = datetime.now().date().isoformat()
    today_tests = c.execute("SELECT COUNT(*) FROM test_sessions WHERE started_at LIKE ?",
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
    return (True, expires) if expires > datetime.now() else (False, expires)

def activate_premium(user_id, username, full_name, days, plan_label):
    now = datetime.now()
    expires = now + timedelta(days=days)
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO premium_users
        (user_id, username, full_name, plan, activated_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, full_name, plan_label, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return expires

def generate_premium_code(days):
    import random, string
    chars = string.ascii_uppercase + string.digits
    uid = ''.join(random.choices(chars, k=6))
    return f"PREM-{uid}-{days}"

def get_all_premium_users():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    rows = c.execute("""SELECT user_id, username, full_name, plan, expires_at
        FROM premium_users ORDER BY expires_at DESC""").fetchall()
    conn.close()
    return rows

# =================== KEYBOARDS ===================
def main_menu(user_id=None):
    ok, _ = is_premium(user_id) if user_id else (False, None)
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
        [KeyboardButton("⭐ Premium faol ✅" if ok else "⭐ Premium haqida")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("ℹ️ Yordam")],
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Testni boshlash")],
        [KeyboardButton("📚 Qoidalar kitobi")],
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
        "✅ Kundalik bepul test topshirish\n"
        "📚 Yo'l harakati qoidalarini o'rganish\n"
        "⭐ Premium — cheksiz test va xatolar tahlili\n\n"
        "Quyidagi menyudan foydalaning 👇"
    )
    kb = admin_menu() if is_admin else main_menu(user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    is_admin = user.id == ADMIN_ID

    # TEST
    if text == "🚗 Testni boshlash":
        save_test_start(user.id)
        ok, expires = is_premium(user.id)
        if ok:
            msg = (
                "🎯 *Premium foydalanuvchi!*\n\n"
                f"⭐ Obunangiz: *{expires.strftime('%d.%m.%Y')}* gacha\n\n"
                "♾ Cheksiz test topshirish faol!\n"
                "🔍 Har bir xato tahlil qilinadi\n\n"
                "👇 Testni boshlang:"
            )
        else:
            msg = (
                "🎯 *Test boshlashga tayyormisiz?*\n\n"
                "📌 Kuniga 1 ta bepul test (20 savol)\n"
                "⏱ Har bir savolga vaqt belgilangan\n"
                "✅ 85% dan yuqori ball — o'tdi!\n\n"
                "⭐ *Premium* bilan cheksiz test va xatolar tahlili!\n\n"
                "👇 Testni boshlang:"
            )
        await update.message.reply_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📝 Testni ochish", url=WEBAPP_URL)
            ]]))

    # QOIDALAR
    elif text == "📚 Qoidalar kitobi":
        await update.message.reply_text(
            "📚 *Yo'l harakati qoidalari*\n\n"
            "O'zbekiston Respublikasining yo'l harakati qoidalari!\n\n"
            "👇 Tugmani bosib o'qing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 Qoidalarni o'qish", url=QOIDALAR_URL)
            ]]))

    # PREMIUM HAQIDA (sotib olish yo'q — faqat ma'lumot)
    elif text in ["⭐ Premium haqida", "⭐ Premium faol ✅"]:
        ok, expires = is_premium(user.id)
        card = get_setting("card_number")
        owner = get_setting("card_owner")
        ctype = get_setting("card_type")
        p1h = int(get_setting("price_1_hafta"))
        p1o = int(get_setting("price_1_oy"))
        p3o = int(get_setting("price_3_oy"))

        if ok:
            await update.message.reply_text(
                f"⭐ *Sizda Premium faol!*\n\n"
                f"📅 Muddati: *{expires.strftime('%d.%m.%Y')}* gacha\n\n"
                "♾ Cheksiz test\n"
                "🔍 Xatolar tahlili\n"
                "🏛 Real imtihon simulyatori\n\n"
                "Yangilash uchun adminga yozing 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✍️ Adminga yozish", url="https://t.me/RuldaTestBot")
                ]]))
        else:
            await update.message.reply_text(
                "⭐ *Premium obuna*\n\n"
                "Premium bilan nimalar ochiladi:\n\n"
                "♾ *Cheksiz test* — kunlik limit yo'q\n"
                "🔍 *Xatolar tahlili* — har xatoga tushuntirish va qonun moddasi\n"
                "🏛 *Real simulyator* — GAI imtihoni muhiti\n"
                "🔔 *Bildirgi* — har xato uchun ogohlantirish\n\n"
                "━━━━━━━━━━━━━━━━\n"
                f"🗓 *1 hafta* — {p1h:,} so'm\n"
                f"🗓 *1 oy* — {p1o:,} so'm\n"
                f"🗓 *3 oy* — {p3o:,} so'm\n"
                "━━━━━━━━━━━━━━━━\n\n"
                f"💳 *{ctype}:* `{card}`\n"
                f"👤 *Egasi:* {owner}\n\n"
                "⚠️ To'lov chekini adminga yuboring:\n"
                "👇 Adminga yozing:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✍️ Adminga yozish", url="https://t.me/RuldaTestBot")
                ]]))

    # STATISTIKA
    elif text == "📊 Statistika":
        total_users, total_tests, today_tests, total_premium = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            f"👥 Jami foydalanuvchilar: *{total_users}* ta\n"
            f"⭐ Premium foydalanuvchilar: *{total_premium}* ta\n"
            f"📝 Jami test boshlangan: *{total_tests}* marta\n"
            f"📅 Bugun test boshlangan: *{today_tests}* marta\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown")

    # YORDAM
    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "ℹ️ *Yordam*\n\n"
            "🚗 *Testni boshlash* — Haydovchilik testini topshirish\n"
            "📚 *Qoidalar kitobi* — Yo'l harakati qoidalari\n"
            "⭐ *Premium* — Cheksiz imkoniyatlar haqida\n"
            "📊 *Statistika* — Umumiy statistika\n\n"
            "❓ Muammo bo'lsa adminga yozing 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✍️ Adminga yozish", url="https://t.me/RuldaTestBot")
            ]]))

    # ADMIN PANEL
    elif text == "🔑 Admin panel" and is_admin:
        total_users, total_tests, today_tests, total_premium = get_stats()
        card = get_setting("card_number")
        owner = get_setting("card_owner")
        ctype = get_setting("card_type")
        p1h = get_setting("price_1_hafta")
        p1o = get_setting("price_1_oy")
        p3o = get_setting("price_3_oy")

        await update.message.reply_text(
            f"🔑 *Admin panel*\n\n"
            f"👥 Foydalanuvchilar: *{total_users}* ta\n"
            f"⭐ Premium: *{total_premium}* ta\n"
            f"📝 Bugun testlar: *{today_tests}* ta\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💳 *Karta:* `{card}`\n"
            f"👤 *Egasi:* {owner}\n"
            f"🏦 *Turi:* {ctype}\n\n"
            f"💰 *Narxlar:*\n"
            f"• 1 hafta: {int(p1h):,} so'm\n"
            f"• 1 oy: {int(p1o):,} so'm\n"
            f"• 3 oy: {int(p3o):,} so'm\n"
            f"━━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Premium berish", callback_data="admin_give_premium")],
                [InlineKeyboardButton("💳 Karta o'zgartirish", callback_data="admin_edit_card")],
                [InlineKeyboardButton("💰 Narx o'zgartirish", callback_data="admin_edit_price")],
                [InlineKeyboardButton("👥 Premium foydalanuvchilar", callback_data="admin_list_premium")],
            ]))

    else:
        await update.message.reply_text(
            "Iltimos, quyidagi menyudan tanlang 👇",
            reply_markup=admin_menu() if is_admin else main_menu(user.id))

# =================== CALLBACK HANDLERS ===================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    # ---- Admin: Premium berish ----
    if data == "admin_give_premium" and user.id == ADMIN_ID:
        context.user_data["admin_state"] = "waiting_user_id"
        await query.message.reply_text(
            "⭐ *Premium berish*\n\n"
            "Foydalanuvchining Telegram ID sini yuboring:\n"
            "(Foydalanuvchi @userinfobot ga /start yozsa ID sini ko'radi)",
            parse_mode="Markdown")

    # ---- Admin: Karta tahrirlash ----
    elif data == "admin_edit_card" and user.id == ADMIN_ID:
        context.user_data["admin_state"] = "edit_card"
        await query.message.reply_text(
            "💳 *Karta ma'lumotlarini tahrirlash*\n\n"
            "Quyidagi formatda yuboring:\n"
            "`karta: 8600 1234 5678 9012`\n"
            "`egasi: Ism Familiya`\n"
            "`turi: Humo / UzCard`\n\n"
            "Har birini alohida xabar sifatida yuboring.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Karta raqam", callback_data="edit_card_number")],
                [InlineKeyboardButton("👤 Karta egasi", callback_data="edit_card_owner")],
                [InlineKeyboardButton("🏦 Karta turi", callback_data="edit_card_type")],
            ]))

    elif data == "edit_card_number" and user.id == ADMIN_ID:
        context.user_data["admin_state"] = "edit_card_number"
        await query.message.reply_text("💳 Yangi karta raqamini yuboring:\n(Masalan: `8600 1234 5678 9012`)", parse_mode="Markdown")

    elif data == "edit_card_owner" and user.id == ADMIN_ID:
        context.user_data["admin_state"] = "edit_card_owner"
        await query.message.reply_text("👤 Karta egasining ismini yuboring:", parse_mode="Markdown")

    elif data == "edit_card_type" and user.id == ADMIN_ID:
        context.user_data["admin_state"] = "edit_card_type"
        await query.message.reply_text(
            "🏦 Karta turini tanlang:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Humo", callback_data="set_card_type_Humo")],
                [InlineKeyboardButton("UzCard", callback_data="set_card_type_UzCard")],
                [InlineKeyboardButton("Humo / UzCard", callback_data="set_card_type_Humo / UzCard")],
            ]))

    elif data.startswith("set_card_type_") and user.id == ADMIN_ID:
        ctype = data.replace("set_card_type_", "")
        set_setting("card_type", ctype)
        await query.edit_message_text(f"✅ Karta turi saqlandi: *{ctype}*", parse_mode="Markdown")

    # ---- Admin: Narx tahrirlash ----
    elif data == "admin_edit_price" and user.id == ADMIN_ID:
        await query.message.reply_text(
            "💰 *Narxlarni tahrirlash*\n\nQaysi narxni o'zgartirmoqchisiz?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"1 hafta ({int(get_setting('price_1_hafta')):,} so'm)", callback_data="edit_price_1_hafta")],
                [InlineKeyboardButton(f"1 oy ({int(get_setting('price_1_oy')):,} so'm)", callback_data="edit_price_1_oy")],
                [InlineKeyboardButton(f"3 oy ({int(get_setting('price_3_oy')):,} so'm)", callback_data="edit_price_3_oy")],
            ]))

    elif data.startswith("edit_price_") and user.id == ADMIN_ID:
        plan = data.replace("edit_price_", "")
        context.user_data["admin_state"] = f"edit_price_{plan}"
        labels = {"1_hafta": "1 hafta", "1_oy": "1 oy", "3_oy": "3 oy"}
        await query.message.reply_text(
            f"💰 *{labels.get(plan, plan)}* uchun yangi narxni yuboring (faqat raqam):\nMasalan: `25000`",
            parse_mode="Markdown")

    # ---- Admin: Premium foydalanuvchilar ----
    elif data == "admin_list_premium" and user.id == ADMIN_ID:
        rows = get_all_premium_users()
        if not rows:
            await query.message.reply_text("⭐ Hozircha premium foydalanuvchilar yo'q.")
            return
        now = datetime.now()
        msg = "⭐ *Premium foydalanuvchilar:*\n\n"
        for uid, uname, fname, plan, exp in rows[:20]:
            expires = datetime.fromisoformat(exp)
            status = "✅" if expires > now else "❌"
            msg += f"{status} *{fname}* (@{uname or 'noma\'lum'})\n"
            msg += f"   📦 {plan} | 📅 {expires.strftime('%d.%m.%Y')}\n\n"
        await query.message.reply_text(msg, parse_mode="Markdown")

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await handle_message(update, context)

    state = context.user_data.get("admin_state", "")
    text = update.message.text.strip()

    # Premium berish — ID kutilmoqda
    if state == "waiting_user_id":
        try:
            target_id = int(text)
            context.user_data["premium_target_id"] = target_id
            context.user_data["admin_state"] = "waiting_days"
            await update.message.reply_text(
                f"✅ ID: `{target_id}`\n\nNecha kun premium bermoqchisiz?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("7 kun", callback_data="give_days_7"),
                     InlineKeyboardButton("30 kun", callback_data="give_days_30")],
                    [InlineKeyboardButton("90 kun", callback_data="give_days_90"),
                     InlineKeyboardButton("365 kun", callback_data="give_days_365")],
                ]))
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri ID! Faqat raqam kiriting.")

    # Karta raqam
    elif state == "edit_card_number":
        set_setting("card_number", text)
        context.user_data["admin_state"] = ""
        await update.message.reply_text(f"✅ Karta raqami saqlandi:\n`{text}`", parse_mode="Markdown")

    # Karta egasi
    elif state == "edit_card_owner":
        set_setting("card_owner", text)
        context.user_data["admin_state"] = ""
        await update.message.reply_text(f"✅ Karta egasi saqlandi: *{text}*", parse_mode="Markdown")

    # Narx tahrirlash
    elif state.startswith("edit_price_"):
        plan = state.replace("edit_price_", "")
        try:
            price = int(text.replace(" ", "").replace(",", ""))
            set_setting(f"price_{plan}", str(price))
            context.user_data["admin_state"] = ""
            labels = {"1_hafta": "1 hafta", "1_oy": "1 oy", "3_oy": "3 oy"}
            await update.message.reply_text(
                f"✅ *{labels.get(plan, plan)}* narxi saqlandi: *{price:,} so'm*",
                parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting! Masalan: 25000")

    else:
        await handle_message(update, context)

async def handle_give_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if user.id != ADMIN_ID:
        return

    data = query.data
    if not data.startswith("give_days_"):
        return await handle_callback(update, context)

    days = int(data.replace("give_days_", ""))
    target_id = context.user_data.get("premium_target_id")
    if not target_id:
        await query.message.reply_text("❌ Xato! Qaytadan boshlang.")
        return

    # Premium kodni yaratish
    code = generate_premium_code(days)
    labels = {7: "1 hafta", 30: "1 oy", 90: "3 oy", 365: "1 yil"}
    plan_label = labels.get(days, f"{days} kun")

    # Premium faollashtirish
    expires = activate_premium(target_id, "", "", days, plan_label)
    context.user_data["admin_state"] = ""
    context.user_data.pop("premium_target_id", None)

    # Foydalanuvchiga xabar yuborish
    try:
        await context.bot.send_message(
            target_id,
            f"🎉 *Tabriklaymiz! Premium faollashtirildi!*\n\n"
            f"📦 Paket: *{plan_label}*\n"
            f"📅 Muddati: *{expires.strftime('%d.%m.%Y')}* gacha\n\n"
            f"🔑 *Sayt uchun premium kod:*\n"
            f"`{code}`\n\n"
            f"📌 *Saytda qanday ishlatish:*\n"
            f"1️⃣ Saytga kiring: avto-test-uz-three.vercel.app\n"
            f"2️⃣ Dashboard da *⭐ Premium* tugmasini bosing\n"
            f"3️⃣ Kodni kiriting\n"
            f"4️⃣ Faollashtirish bosing\n\n"
            f"♾ Cheksiz test\n"
            f"🔍 Xatolar tahlili\n"
            f"🔔 Har xato uchun bildirgi\n\n"
            f"Omad! 🚗",
            parse_mode="Markdown")
        await query.edit_message_text(
            f"✅ *Premium berildi!*\n\n"
            f"🆔 ID: `{target_id}`\n"
            f"📦 Paket: *{plan_label}*\n"
            f"📅 {expires.strftime('%d.%m.%Y')} gacha\n"
            f"🔑 Kod: `{code}`",
            parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(
            f"⚠️ Premium berildi lekin xabar yuborilmadi!\n"
            f"🆔 ID: `{target_id}` topilmadi.\n"
            f"🔑 Kod: `{code}`\n"
            f"Kodni qo'lda yuboring!",
            parse_mode="Markdown")

# =================== RECEIPT PHOTO =====================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    caption = update.message.caption or ""
    try:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=(
                f"📤 *To'lov cheki keldi!*\n\n"
                f"👤 *{user.full_name}* (@{user.username or 'noma\'lum'})\n"
                f"🆔 ID: `{user.id}`\n"
                f"📝 Izoh: {caption or 'yo\'q'}\n\n"
                f"Premium berish uchun: 🔑 Admin panel → ⭐ Premium berish → ID: `{user.id}`"
            ),
            parse_mode="Markdown")
        await update.message.reply_text(
            "✅ To'lov chekingiz adminga yuborildi!\n"
            "Tez orada premium faollashtiriladi.")
    except Exception as e:
        logger.error(f"Chek yuborishda xato: {e}")

# =================== MAIN ===================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_give_days_callback, pattern="^give_days_"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
