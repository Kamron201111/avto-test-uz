"""
AvtoTest.Uz Telegram Bot
Bot token: 8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM
Admin: @kamron201 (ID: 6498632307)

Kutubxonalar:
  pip install python-telegram-bot==20.7 supabase python-dotenv
"""

import os
import asyncio
import random
import json
from datetime import datetime, date
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from supabase import create_client, Client

load_dotenv()

# =================== CONFIG ===================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6498632307"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bwdnvxucvyeknesifnwg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://avto-test-uz-three.vercel.app")
FREE_DAILY_LIMIT = 20

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =================== STATES ===================
QUIZ_ANSWERING = 1
SUPPORT_MESSAGE = 2

# =================== HELPERS ===================

def get_user_id(telegram_id: int) -> str:
    return f"user_{telegram_id}"

async def is_premium(telegram_id: int) -> bool:
    try:
        uid = get_user_id(telegram_id)
        res = supabase.table("premium_users").select("expires_at").eq("user_id", uid).single().execute()
        if res.data:
            return datetime.fromisoformat(res.data["expires_at"].replace("Z", "+00:00")) > datetime.now().astimezone()
        return False
    except:
        return False

async def get_daily_used(telegram_id: int) -> int:
    try:
        uid = get_user_id(telegram_id)
        today = date.today().isoformat()
        res = supabase.table("daily_tests").select("count").eq("user_id", uid).eq("test_date", today).single().execute()
        return res.data["count"] if res.data else 0
    except:
        return 0

async def increment_daily(telegram_id: int):
    try:
        uid = get_user_id(telegram_id)
        today = date.today().isoformat()
        res = supabase.table("daily_tests").select("count").eq("user_id", uid).eq("test_date", today).single().execute()
        if res.data:
            supabase.table("daily_tests").update({"count": res.data["count"] + 1}).eq("user_id", uid).eq("test_date", today).execute()
        else:
            supabase.table("daily_tests").insert({"user_id": uid, "test_date": today, "count": 1}).execute()
    except:
        pass

async def get_random_questions(count: int = 10, category: str = None) -> list:
    try:
        query = supabase.table("questions").select("*")
        if category:
            query = query.eq("category", category)
        res = query.execute()
        questions = res.data or []
        random.shuffle(questions)
        return questions[:count]
    except:
        return []

async def ensure_user_exists(update: Update):
    """Foydalanuvchini Supabase da yaratish yoki yangilash"""
    user = update.effective_user
    uid = get_user_id(user.id)
    try:
        res = supabase.table("users").select("id").eq("id", uid).single().execute()
        if not res.data:
            supabase.table("users").insert({
                "id": uid,
                "name": user.first_name or user.username or "Foydalanuvchi",
                "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "role": "USER",
                "total_points": 0,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
            }).execute()
        else:
            supabase.table("users").update({"last_active": datetime.now().isoformat()}).eq("id", uid).execute()
    except:
        pass

# =================== KEYBOARDS ===================

def main_menu_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton("🚗 Test boshlash"), KeyboardButton("📚 Kategoriyalar")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("⭐ Premium")],
        [KeyboardButton("📖 YHQ Kitob"), KeyboardButton("🌐 Saytga o'tish")],
        [KeyboardButton("📞 Aloqa / Support")],
    ]
    if is_admin:
        buttons.append([KeyboardButton("🔑 Admin Panel")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def categories_keyboard():
    cats = [
        ("📚 Umumiy", "umumiy"),
        ("🚦 Yo'l Belgilari", "belgilar"),
        ("📖 Qoidalar", "qoidalar"),
        ("🛡️ Xavfsizlik", "xavfsizlik"),
        ("🔧 Texnik", "texnik"),
        ("❤️ Birinchi Yordam", "birinchi-yordam"),
        ("⚠️ Jarimalar", "jarimalar"),
    ]
    buttons = []
    for i in range(0, len(cats), 2):
        row = []
        for name, cat in cats[i:i+2]:
            row.append(InlineKeyboardButton(name, callback_data=f"cat_{cat}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def question_count_keyboard(category=None):
    prefix = f"start_{category}" if category else "start_all"
    buttons = [
        [
            InlineKeyboardButton("10 savol", callback_data=f"{prefix}_10"),
            InlineKeyboardButton("20 savol", callback_data=f"{prefix}_20"),
        ],
        [
            InlineKeyboardButton("30 savol", callback_data=f"{prefix}_30"),
            InlineKeyboardButton("40 savol", callback_data=f"{prefix}_40"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_cats")],
    ]
    return InlineKeyboardMarkup(buttons)

def answer_keyboard(options: dict, question_id: str, answered=False):
    label_map = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
    buttons = []
    for key, text in options.items():
        if key == "E" and not text:
            continue
        short = text[:35] + "..." if len(text) > 35 else text
        label = label_map.get(key, key)
        if not answered:
            buttons.append([InlineKeyboardButton(f"{label}. {short}", callback_data=f"ans_{question_id}_{key}")])
    if answered:
        buttons.append([InlineKeyboardButton("▶️ Keyingi savol", callback_data="next_q")])
    return InlineKeyboardMarkup(buttons)

def premium_keyboard():
    buttons = [
        [InlineKeyboardButton("⭐ 1 Hafta", callback_data="buy_hafta"),
         InlineKeyboardButton("⭐ 1 Oy", callback_data="buy_oy")],
        [InlineKeyboardButton("👑 1 Yil — TEJAM!", callback_data="buy_yil")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

def webapp_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🌐 Saytni ochish", web_app=WebAppInfo(url=WEB_APP_URL))
    ]])

# =================== /START ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_exists(update)
    is_admin = user.id == ADMIN_ID
    premium = await is_premium(user.id)

    badge = "👑 Premium" if premium else "🆓 Bepul"
    text = (
        f"🚗 *AvtoTest.Uz ga xush kelibsiz!*\n\n"
        f"Salom, *{user.first_name}*! {badge}\n\n"
        f"🎯 O'zbekistonda haydovchilik imtihoniga tayyorlanish uchun eng yaxshi platforma!\n\n"
        f"📌 *Nimalar bor?*\n"
        f"• 1000+ test savollari\n"
        f"• 7 ta kategoriya\n"
        f"• Kunlik {FREE_DAILY_LIMIT} ta bepul test\n"
        f"• YHQ kitob (PDF)\n"
        f"• Premium: cheksiz test + video kurslar\n\n"
        f"Pastdagi tugmalardan foydalaning 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin)
    )

# =================== TEST BOSHLASH ===================

async def handle_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    premium = await is_premium(user.id)
    used = await get_daily_used(user.id)

    if not premium and used >= FREE_DAILY_LIMIT:
        text = (
            f"⛔ *Kunlik limit tugadi!*\n\n"
            f"Bugun {used}/{FREE_DAILY_LIMIT} ta testni ishladingiz.\n\n"
            f"Premium obuna bilan:\n"
            f"✅ Cheksiz kunlik test\n"
            f"✅ Video kurslar\n"
            f"✅ YHQ barcha boblari\n\n"
            f"Ertaga yana bepul testlar ochiladi 🕐"
        )
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=premium_keyboard())
        return

    remaining = "♾️ Cheksiz" if premium else f"{FREE_DAILY_LIMIT - used} ta qoldi"
    text = (
        f"📝 *Test boshlash*\n\n"
        f"📊 Bugungi limit: *{remaining}*\n\n"
        f"Nechta savol ishlashni xohlaysiz?"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=question_count_keyboard()
    )

# =================== KATEGORIYALAR ===================

async def handle_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Kategoriya tanlang:*\n\nHar bir kategoriyadan alohida test ishlashingiz mumkin.",
        parse_mode="Markdown",
        reply_markup=categories_keyboard()
    )

# =================== STATISTIKA ===================

async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = get_user_id(user.id)
    premium = await is_premium(user.id)
    used = await get_daily_used(user.id)

    try:
        results = supabase.table("test_results").select("*").eq("user_id", uid).order("date", desc=True).limit(50).execute()
        data = results.data or []

        total_tests = len(data)
        if total_tests > 0:
            avg_score = round(sum(r["score_percentage"] for r in data) / total_tests)
            passed = sum(1 for r in data if r["score_percentage"] >= 85)
            total_time = sum(r.get("time_spent_seconds", 0) for r in data)
            hours = total_time // 3600
            minutes = (total_time % 3600) // 60
            best_score = max(r["score_percentage"] for r in data)
            last_result = data[0]
            last_score = last_result["score_percentage"]
            last_date = last_result["date"][:10]
        else:
            avg_score = passed = hours = minutes = best_score = last_score = 0
            last_date = "Hali yo'q"

        user_data = supabase.table("users").select("total_points").eq("id", uid).single().execute()
        points = user_data.data.get("total_points", 0) if user_data.data else 0

        badge = "👑 Premium" if premium else "🆓 Bepul"
        remaining = "♾️" if premium else f"{FREE_DAILY_LIMIT - used}/{FREE_DAILY_LIMIT}"

        text = (
            f"📊 *Sizning statistikangiz*\n\n"
            f"👤 {user.first_name} • {badge}\n"
            f"⚡ Bugungi limit: {remaining}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🧪 Jami testlar: *{total_tests}* ta\n"
            f"✅ O'tgan testlar: *{passed}* ta (≥85%)\n"
            f"📈 O'rtacha ball: *{avg_score}%*\n"
            f"🏆 Eng yaxshi natija: *{best_score}%*\n"
            f"⏱ Umumiy vaqt: *{hours}h {minutes}m*\n"
            f"⭐ Jami ball: *{points}*\n\n"
            f"📅 Oxirgi test: {last_score}% • {last_date}"
        )
    except Exception as e:
        text = f"📊 *Statistika*\n\nHali hech qanday test topshirilmagan.\n\nBoshlash uchun /test ni bosing!"

    await update.message.reply_text(text, parse_mode="Markdown")

# =================== PREMIUM ===================

async def handle_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    premium = await is_premium(user.id)

    if premium:
        try:
            res = supabase.table("premium_users").select("expires_at", "plan").eq("user_id", get_user_id(user.id)).single().execute()
            expires = res.data["expires_at"][:10] if res.data else "Noma'lum"
            plan = res.data.get("plan", "Premium") if res.data else "Premium"
        except:
            expires = "Noma'lum"
            plan = "Premium"

        text = (
            f"👑 *Premium Faol!*\n\n"
            f"📦 Tarif: *{plan}*\n"
            f"📅 Muddati: *{expires}* gacha\n\n"
            f"✅ Cheksiz kunlik test\n"
            f"✅ Barcha video kurslar\n"
            f"✅ YHQ barcha 29 bob\n"
            f"✅ Batafsil statistika"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    try:
        settings = supabase.table("settings").select("key", "value").in_("key", ["price_1_hafta", "price_1_oy", "price_1_yil"]).execute()
        prices = {r["key"]: r["value"] for r in (settings.data or [])}
    except:
        prices = {}

    p_hafta = int(prices.get("price_1_hafta", 15000))
    p_oy = int(prices.get("price_1_oy", 49000))
    p_yil = int(prices.get("price_1_yil", 149000))

    text = (
        f"⭐ *Premium Obuna*\n\n"
        f"Premium bilan nimalarga ega bo'lasiz:\n"
        f"✅ Cheksiz kunlik testlar\n"
        f"✅ Barcha video kurslar (20 ta dars)\n"
        f"✅ YHQ kitob — barcha 29 bob\n"
        f"✅ Batafsil tahlil va statistika\n\n"
        f"💰 *Narxlar:*\n"
        f"• 1 Hafta — *{p_hafta:,} so'm*\n"
        f"• 1 Oy — *{p_oy:,} so'm* 🔥\n"
        f"• 1 Yil — *{p_yil:,} so'm* 💎\n\n"
        f"To'lov qilish uchun tarif tanlang 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=premium_keyboard())

# =================== SAYTGA O'TISH ===================

async def handle_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"🌐 *AvtoTest.Uz Sayti*\n\n"
        f"Saytda nimalar bor:\n"
        f"• To'liq test tizimi\n"
        f"• Video kurslar\n"
        f"• YHQ kitob va boblar\n"
        f"• Batafsil statistika\n"
        f"• Premium boshqaruv\n\n"
        f"Quyidagi tugmani bosing 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=webapp_keyboard())

# =================== SUPPORT ===================

async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📞 *Muammo yoki savol bormi?*\n\n"
        f"Xabaringizni yozing, admin tez orada javob beradi!\n\n"
        f"Yoki to'g'ridan: @kamron201"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_support")]])
    )
    return SUPPORT_MESSAGE

async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message.text

    # Adminga yuborish
    text = (
        f"📩 *Yangi xabar!*\n\n"
        f"👤 Foydalanuvchi: [{user.first_name}](tg://user?id={user.id})\n"
        f"🆔 ID: `{user.id}`\n"
        f"📅 Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"💬 Xabar:\n{msg}"
    )
    try:
        await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except:
        pass

    await update.message.reply_text(
        "✅ Xabaringiz adminга yuborildi!\n\nTez orada javob beriladi.",
        reply_markup=main_menu_keyboard(user.id == ADMIN_ID)
    )
    return ConversationHandler.END

# =================== ADMIN PANEL ===================

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Ruxsat yo'q!")
        return

    try:
        users_res = supabase.table("users").select("id", count="exact").neq("role", "ADMIN").execute()
        questions_res = supabase.table("questions").select("id", count="exact").execute()
        tests_res = supabase.table("test_results").select("id", count="exact").execute()
        premium_res = supabase.table("premium_users").select("id", count="exact").gt("expires_at", datetime.now().isoformat()).execute()
        pending_res = supabase.table("premium_requests").select("id", count="exact").eq("status", "pending").execute()

        total_users = users_res.count or 0
        total_q = questions_res.count or 0
        total_tests = tests_res.count or 0
        active_premium = premium_res.count or 0
        pending = pending_res.count or 0
    except:
        total_users = total_q = total_tests = active_premium = pending = 0

    text = (
        f"🔑 *Admin Panel*\n\n"
        f"👥 Foydalanuvchilar: *{total_users}*\n"
        f"📝 Savollar: *{total_q}*\n"
        f"🧪 Testlar: *{total_tests}*\n"
        f"👑 Aktiv Premium: *{active_premium}*\n"
        f"⏳ Kutilayotgan so'rovlar: *{pending}*\n\n"
        f"{'🔴 ' + str(pending) + ' ta yangi premium so'rov bor!' if pending > 0 else '✅ Yangi so'rovlar yo'q'}"
    )

    buttons = [
        [InlineKeyboardButton(f"⏳ Premium so'rovlar ({pending})", callback_data="admin_pending")],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users"),
         InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

# =================== CALLBACK HANDLERS ===================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # Kategoriya tanlash
    if data.startswith("cat_"):
        cat = data[4:]
        cat_names = {
            "umumiy": "📚 Umumiy",
            "belgilar": "🚦 Yo'l Belgilari",
            "qoidalar": "📖 Qoidalar",
            "xavfsizlik": "🛡️ Xavfsizlik",
            "texnik": "🔧 Texnik",
            "birinchi-yordam": "❤️ Birinchi Yordam",
            "jarimalar": "⚠️ Jarimalar",
        }
        context.user_data["category"] = cat
        name = cat_names.get(cat, cat)
        await query.edit_message_text(
            f"*{name}* kategoriyasi tanlandi!\n\nNechta savol?",
            parse_mode="Markdown",
            reply_markup=question_count_keyboard(cat)
        )

    # Test boshlash (savol soni tanlash)
    elif data.startswith("start_"):
        parts = data.split("_")
        count = int(parts[-1])
        category = "_".join(parts[1:-1]) if parts[1] != "all" else None

        # Limit tekshirish
        premium = await is_premium(user.id)
        used = await get_daily_used(user.id)

        if not premium and used >= FREE_DAILY_LIMIT:
            await query.edit_message_text(
                f"⛔ *Kunlik limit tugadi!*\n\nBugun {FREE_DAILY_LIMIT} ta test ishladingiz.\nErtaga yana bepul!",
                parse_mode="Markdown",
                reply_markup=premium_keyboard()
            )
            return

        # Savollarni olish
        questions = await get_random_questions(count, category)
        if not questions:
            await query.edit_message_text("❌ Savollar topilmadi. Keyinroq urinib ko'ring.")
            return

        # Test ma'lumotlarini saqlash
        context.user_data["quiz"] = {
            "questions": questions,
            "current": 0,
            "answers": {},
            "correct": 0,
            "start_time": datetime.now().isoformat(),
            "category": category,
        }

        await query.delete_message()
        await send_question(update, context)
        return

    # Javob berish
    elif data.startswith("ans_"):
        _, qid, ans_key = data.split("_", 2)
        quiz = context.user_data.get("quiz")
        if not quiz:
            await query.edit_message_text("❌ Test topilmadi. /start bosing.")
            return

        current_q = quiz["questions"][quiz["current"]]
        if current_q["id"] == qid and qid not in quiz["answers"]:
            quiz["answers"][qid] = ans_key
            correct = ans_key == current_q["correct_answer"]
            if correct:
                quiz["correct"] += 1

            # Natijani ko'rsatish
            label_map = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
            options = {
                "A": current_q["option_a"],
                "B": current_q["option_b"],
                "C": current_q["option_c"],
                "D": current_q["option_d"],
            }
            if current_q.get("option_e"):
                options["E"] = current_q["option_e"]

            result_text = "✅ *To'g'ri!*" if correct else f"❌ *Noto'g'ri!*\n\nTo'g'ri javob: **{label_map[current_q['correct_answer']]}. {options[current_q['correct_answer']]}**"

            if current_q.get("description"):
                result_text += f"\n\n💡 *Izoh:* {current_q['description']}"

            total = len(quiz["questions"])
            answered = len(quiz["answers"])
            result_text += f"\n\n📊 {answered}/{total} savol"

            # Faqat "Keyingi" tugma
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Keyingi savol", callback_data="next_q")]])
            await query.edit_message_text(result_text, parse_mode="Markdown", reply_markup=kb)

    # Keyingi savol
    elif data == "next_q":
        quiz = context.user_data.get("quiz")
        if not quiz:
            return
        quiz["current"] += 1
        if quiz["current"] >= len(quiz["questions"]):
            await finish_quiz(update, context)
        else:
            await query.delete_message()
            await send_question(update, context)

    # Premium xarid
    elif data.startswith("buy_"):
        plan_key = data[4:]
        plan_names = {"hafta": "1 Hafta", "oy": "1 Oy", "yil": "1 Yil"}
        price_keys = {"hafta": "price_1_hafta", "oy": "price_1_oy", "yil": "price_1_yil"}

        try:
            settings = supabase.table("settings").select("key", "value").in_("key", list(price_keys.values())).execute()
            prices = {r["key"]: r["value"] for r in (settings.data or [])}
            card_res = supabase.table("settings").select("key", "value").in_("key", ["card_number", "card_owner", "card_type"]).execute()
            card = {r["key"]: r["value"] for r in (card_res.data or [])}
        except:
            prices = {}
            card = {}

        default_prices = {"price_1_hafta": "15000", "price_1_oy": "49000", "price_1_yil": "149000"}
        price = int(prices.get(price_keys[plan_key], default_prices[price_keys[plan_key]]))
        plan_name = plan_names[plan_key]

        card_number = card.get("card_number", "8600 0000 0000 0000")
        card_owner = card.get("card_owner", "Valiyev Kamron")
        card_type = card.get("card_type", "Humo")

        text = (
            f"💳 *{plan_name} — {price:,} so'm*\n\n"
            f"To'lov qilish:\n"
            f"🏦 Karta: `{card_number}`\n"
            f"👤 Egasi: {card_owner}\n"
            f"💳 Turi: {card_type}\n\n"
            f"📌 *Qadamlar:*\n"
            f"1️⃣ Yuqoridagi kartaga {price:,} so'm o'tkazing\n"
            f"2️⃣ To'lov chekini screenshot qiling\n"
            f"3️⃣ @kamron201 ga yuboring\n"
            f"4️⃣ Admin tasdiqlaydi — Premium faollashadi!\n\n"
            f"⏱ Tasdiqlash vaqti: 1-24 soat"
        )
        buttons = [
            [InlineKeyboardButton("📸 Chekni yuborish", url=f"https://t.me/kamron201")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_premium")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    # Admin: kutilayotgan so'rovlar
    elif data == "admin_pending" and user.id == ADMIN_ID:
        try:
            res = supabase.table("premium_requests").select("*").eq("status", "pending").order("created_at", desc=True).limit(10).execute()
            requests = res.data or []
        except:
            requests = []

        if not requests:
            await query.edit_message_text("✅ Kutilayotgan premium so'rovlar yo'q.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_admin")]]))
            return

        for req in requests[:5]:
            text = (
                f"📋 *Premium So'rov*\n\n"
                f"👤 {req.get('user_name', 'Noma\'lum')}\n"
                f"📦 Tarif: {req.get('plan', '')}\n"
                f"💰 Narx: {req.get('price', 0):,} so'm\n"
                f"📅 Sana: {req.get('created_at', '')[:10]}"
            )
            buttons = [
                [
                    InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{req['id']}"),
                    InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{req['id']}"),
                ]
            ]
            await context.bot.send_message(
                ADMIN_ID, text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        await query.edit_message_text(f"📋 {len(requests)} ta so'rov yuborildi.")

    # Admin: tasdiqlash
    elif data.startswith("approve_") and user.id == ADMIN_ID:
        req_id = data[8:]
        try:
            req = supabase.table("premium_requests").select("*").eq("id", req_id).single().execute().data
            if req:
                # Premiumni faollashtirish
                from datetime import timedelta
                days = req.get("days", 30)
                expires = (datetime.now() + timedelta(days=days)).isoformat()
                supabase.table("premium_users").upsert({
                    "user_id": req["user_id"],
                    "plan": req["plan"],
                    "activated_at": datetime.now().isoformat(),
                    "expires_at": expires,
                }, on_conflict="user_id").execute()
                supabase.table("premium_requests").update({"status": "approved"}).eq("id", req_id).execute()

                # Foydalanuvchiga xabar
                tg_id_str = req["user_id"].replace("user_", "")
                try:
                    tg_id = int(tg_id_str.split("_")[0])
                    await context.bot.send_message(
                        tg_id,
                        f"🎉 *Premium faollashdi!*\n\n"
                        f"Tarif: *{req['plan']}*\n"
                        f"Muddat: *{days} kun* ({expires[:10]} gacha)\n\n"
                        f"✅ Cheksiz test\n✅ Video kurslar\n✅ YHQ barcha boblari\n\n"
                        f"Rahmat! 🚗",
                        parse_mode="Markdown"
                    )
                except:
                    pass

                await query.edit_message_text(f"✅ {req.get('user_name')} uchun premium faollashdi!")
        except Exception as e:
            await query.edit_message_text(f"❌ Xato: {e}")

    # Admin: rad etish
    elif data.startswith("reject_") and user.id == ADMIN_ID:
        req_id = data[7:]
        try:
            req = supabase.table("premium_requests").select("*").eq("id", req_id).single().execute().data
            if req:
                supabase.table("premium_requests").update({"status": "rejected"}).eq("id", req_id).execute()
                tg_id_str = req["user_id"].replace("user_", "")
                try:
                    tg_id = int(tg_id_str.split("_")[0])
                    await context.bot.send_message(
                        tg_id,
                        f"❌ *So'rovingiz rad etildi*\n\n"
                        f"Sabab: To'lov tasdiqlanmadi.\n\n"
                        f"Muammo bo'lsa @kamron201 ga murojaat qiling.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                await query.edit_message_text(f"❌ {req.get('user_name')} rad etildi.")
        except Exception as e:
            await query.edit_message_text(f"❌ Xato: {e}")

    # Orqaga tugmalar
    elif data == "back_main":
        await query.delete_message()
    elif data == "back_cats":
        await query.edit_message_text("📚 *Kategoriya tanlang:*", parse_mode="Markdown", reply_markup=categories_keyboard())
    elif data == "back_premium":
        await handle_premium(update, context)
    elif data == "cancel_support":
        await query.edit_message_text("❌ Bekor qilindi.")

# =================== QUIZ FUNKSIYALARI ===================

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = context.user_data.get("quiz")
    if not quiz:
        return

    q = quiz["questions"][quiz["current"]]
    idx = quiz["current"]
    total = len(quiz["questions"])
    answered = len(quiz["answers"])
    correct = quiz["correct"]

    options = {
        "A": q["option_a"],
        "B": q["option_b"],
        "C": q["option_c"],
        "D": q["option_d"],
    }
    if q.get("option_e"):
        options["E"] = q["option_e"]

    label_map = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
    options_text = "\n".join([f"*{label_map[k]}.* {v}" for k, v in options.items() if v])

    progress_bar = "".join(["🟢" if i < idx else "⚪" for i in range(min(total, 10))])

    text = (
        f"❓ *Savol {idx + 1}/{total}*\n"
        f"{progress_bar}\n"
        f"✅ {correct} to'g'ri\n\n"
        f"*{q['question_text']}*\n\n"
        f"{options_text}"
    )

    kb = answer_keyboard(options, q["id"])

    chat_id = update.effective_chat.id
    if q.get("image"):
        try:
            await context.bot.send_photo(chat_id, q["image"], caption=text, parse_mode="Markdown", reply_markup=kb)
            return
        except:
            pass

    await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = context.user_data.get("quiz")
    if not quiz:
        return

    user = update.effective_user
    total = len(quiz["questions"])
    correct = quiz["correct"]
    score = round((correct / total) * 100) if total > 0 else 0

    # Natijani Supabase ga saqlash
    try:
        start_time = datetime.fromisoformat(quiz["start_time"])
        time_spent = int((datetime.now() - start_time).total_seconds())

        details = []
        for q in quiz["questions"]:
            user_ans = quiz["answers"].get(q["id"], "")
            details.append({
                "questionId": q["id"],
                "userAnswer": user_ans,
                "correctAnswer": q["correct_answer"],
                "isCorrect": user_ans == q["correct_answer"],
            })

        uid = get_user_id(user.id)
        supabase.table("test_results").insert({
            "id": f"tg_{user.id}_{int(datetime.now().timestamp())}",
            "user_id": uid,
            "date": datetime.now().isoformat(),
            "total_questions": total,
            "correct_count": correct,
            "score_percentage": score,
            "time_spent_seconds": time_spent,
            "details": details,
        }).execute()

        # Ballarni yangilash
        u_res = supabase.table("users").select("total_points").eq("id", uid).single().execute()
        if u_res.data:
            supabase.table("users").update({"total_points": (u_res.data["total_points"] or 0) + score}).eq("id", uid).execute()

        # Kunlik limitni oshirish
        await increment_daily(user.id)
    except Exception as e:
        pass

    # Natija matni
    passed = score >= 85
    emoji = "🎉" if passed else "😔"
    status = "O'TDINGIZ!" if passed else "O'TMADINGIZ"

    stars = "⭐" * (score // 20)

    text = (
        f"{emoji} *Test yakunlandi!*\n\n"
        f"{'✅' if passed else '❌'} *{status}*\n\n"
        f"📊 Natija: *{correct}/{total}* to'g'ri\n"
        f"📈 Ball: *{score}%*\n"
        f"{stars}\n\n"
    )

    if passed:
        text += "🎊 Zo'r natija! Davom eting!\n"
    elif score >= 70:
        text += "👍 Yaxshi harakat! Yana bir marta urinib ko'ring.\n"
    else:
        text += "📚 Ko'proq o'qing va qaytadan urinib ko'ring.\n"

    used = await get_daily_used(user.id)
    premium = await is_premium(user.id)
    remaining = "♾️ Cheksiz" if premium else f"{FREE_DAILY_LIMIT - used} ta qoldi"
    text += f"\n📊 Bugungi limit: {remaining}"

    buttons = [
        [InlineKeyboardButton("🔄 Yana test", callback_data="start_all_10"),
         InlineKeyboardButton("📊 Statistika", callback_data="show_stats")],
    ]
    if not premium:
        buttons.append([InlineKeyboardButton("⭐ Premium olish", callback_data="show_premium")])

    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    context.user_data.pop("quiz", None)

# =================== MESSAGE HANDLER ===================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🚗 Test boshlash":
        await handle_test_start(update, context)
    elif text == "📚 Kategoriyalar":
        await handle_categories(update, context)
    elif text == "📊 Statistika":
        await handle_stats(update, context)
    elif text == "⭐ Premium":
        await handle_premium(update, context)
    elif text == "🌐 Saytga o'tish":
        await handle_webapp(update, context)
    elif text == "📖 YHQ Kitob":
        await update.message.reply_text(
            "📖 *YHQ — Yo'l Harakati Qoidalari*\n\n"
            "Barcha 29 bob saytda mavjud.\n"
            "Premium foydalanuvchilar barcha boblarni o'qiy oladi!\n\n"
            "Saytga o'ting 👇",
            parse_mode="Markdown",
            reply_markup=webapp_keyboard()
        )
    elif text == "📞 Aloqa / Support":
        return await handle_support(update, context)
    elif text == "🔑 Admin Panel" and user.id == ADMIN_ID:
        await handle_admin(update, context)
    else:
        await update.message.reply_text(
            "Pastdagi tugmalardan foydalaning 👇",
            reply_markup=main_menu_keyboard(user.id == ADMIN_ID)
        )

# =================== COMMANDS ===================

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_test_start(update, context)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_stats(update, context)

async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_premium(update, context)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *AvtoTest.Uz Bot — Yordam*\n\n"
        "📌 *Asosiy buyruqlar:*\n"
        "/start — Bosh menu\n"
        "/test — Test boshlash\n"
        "/stats — Statistika\n"
        "/premium — Premium ma'lumot\n"
        "/help — Yordam\n\n"
        "📌 *Qanday ishlaydi?*\n"
        "1. Test boshlang\n"
        "2. Savolga javob bering\n"
        "3. Natijangizni ko'ring\n"
        "4. Kuniga 20 ta bepul test!\n\n"
        "Savollar bo'lsa: @kamron201"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# =================== MAIN ===================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Support conversation
    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📞 Aloqa / Support$"), handle_support)],
        states={SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_message)]},
        fallbacks=[CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="cancel_support")],
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(support_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🚗 AvtoTest.Uz Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
