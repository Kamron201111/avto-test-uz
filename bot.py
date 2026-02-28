"""
╔══════════════════════════════════════════════╗
║        AvtoTest.Uz - Telegram Bot v3.0        ║
║   To'liq test tizimi + Admin + Premium        ║
╚══════════════════════════════════════════════╝
"""

import os, random, logging, asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ╔══════════════════════════════════════════════╗
# ║                  CONFIG                       ║
# ╚══════════════════════════════════════════════╝
BOT_TOKEN    = os.getenv("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "1935541521"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bwdnvxucvyeknesifnwg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "https://avto-test-uz-three.vercel.app")
FREE_LIMIT   = 20
PASS_SCORE   = 85

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ConversationHandler states
SUPPORT_WAIT        = 1
BROADCAST_WAIT      = 2
GIVE_PREMIUM_ID     = 3
GIVE_PREMIUM_DAYS   = 4

# ╔══════════════════════════════════════════════╗
# ║              SUPABASE HELPERS                 ║
# ╚══════════════════════════════════════════════╝
def uid(tg_id: int) -> str:
    return f"user_{tg_id}"

async def is_premium(tg_id: int) -> bool:
    try:
        r = sb.table("premium_users").select("expires_at").eq("user_id", uid(tg_id)).single().execute()
        if r.data:
            exp = r.data["expires_at"].replace("Z", "+00:00")
            return datetime.fromisoformat(exp) > datetime.now().astimezone()
    except: pass
    return False

async def get_premium_info(tg_id: int) -> dict:
    try:
        r = sb.table("premium_users").select("*").eq("user_id", uid(tg_id)).single().execute()
        if r.data:
            exp = datetime.fromisoformat(r.data["expires_at"].replace("Z", "+00:00"))
            return {
                "active": exp > datetime.now().astimezone(),
                "expires": exp.strftime("%d.%m.%Y"),
                "plan": r.data.get("plan", "Premium"),
                "days_left": max(0, (exp.date() - date.today()).days)
            }
    except: pass
    return {"active": False}

async def get_daily_used(tg_id: int) -> int:
    try:
        today = date.today().isoformat()
        r = sb.table("daily_tests").select("count").eq("user_id", uid(tg_id)).eq("test_date", today).single().execute()
        return r.data["count"] if r.data else 0
    except: return 0

async def increment_daily(tg_id: int):
    try:
        today = date.today().isoformat()
        r = sb.table("daily_tests").select("count").eq("user_id", uid(tg_id)).eq("test_date", today).single().execute()
        if r.data:
            sb.table("daily_tests").update({"count": r.data["count"] + 1}).eq("user_id", uid(tg_id)).eq("test_date", today).execute()
        else:
            sb.table("daily_tests").insert({"user_id": uid(tg_id), "test_date": today, "count": 1}).execute()
    except: pass

async def ensure_user(update: Update):
    u = update.effective_user
    try:
        r = sb.table("users").select("id").eq("id", uid(u.id)).single().execute()
        now = datetime.now().isoformat()
        if not r.data:
            sb.table("users").insert({
                "id": uid(u.id),
                "name": u.first_name or u.username or "Foydalanuvchi",
                "full_name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
                "role": "USER", "total_points": 0,
                "created_at": now, "last_active": now,
            }).execute()
        else:
            sb.table("users").update({"last_active": now}).eq("id", uid(u.id)).execute()
    except: pass

async def fetch_questions(count: int, category: str = None) -> list:
    try:
        q = sb.table("questions").select("*")
        if category and category != "all":
            q = q.eq("category", category)
        r = q.execute()
        qs = r.data or []
        random.shuffle(qs)
        return qs[:count]
    except: return []

async def get_setting(key: str, default: str = "") -> str:
    try:
        r = sb.table("settings").select("value").eq("key", key).single().execute()
        return r.data["value"] if r.data else default
    except: return default

async def get_settings(*keys) -> dict:
    try:
        r = sb.table("settings").select("key,value").in_("key", list(keys)).execute()
        return {row["key"]: row["value"] for row in (r.data or [])}
    except: return {}

async def get_user_stats(tg_id: int) -> dict:
    try:
        r = sb.table("test_results").select("*").eq("user_id", uid(tg_id)).order("date", desc=True).limit(100).execute()
        data = r.data or []
        if not data:
            return {"total": 0}
        total = len(data)
        passed = sum(1 for d in data if d["score_percentage"] >= PASS_SCORE)
        avg = round(sum(d["score_percentage"] for d in data) / total)
        best = max(d["score_percentage"] for d in data)
        worst = min(d["score_percentage"] for d in data)
        time_total = sum(d.get("time_spent_seconds", 0) for d in data)

        # Streak hisoblash
        streak = 0
        used_dates = sorted(set(d["date"][:10] for d in data), reverse=True)
        check = date.today()
        for ds in used_dates:
            if date.fromisoformat(ds) == check:
                streak += 1
                check -= timedelta(days=1)
            else: break

        ur = sb.table("users").select("total_points").eq("id", uid(tg_id)).single().execute()
        points = ur.data.get("total_points", 0) if ur.data else 0

        # Kategoriya bo'yicha tahlil
        cat_stats = {}
        for d in data:
            details = d.get("details", [])
            if details:
                pass  # murakkab tahlil keyinroq

        return {
            "total": total, "passed": passed, "failed": total - passed,
            "avg": avg, "best": best, "worst": worst,
            "time": time_total, "points": points, "streak": streak,
            "pass_rate": round(passed / total * 100) if total else 0,
            "recent": data[:3]
        }
    except: return {"total": 0}

async def get_leaderboard() -> list:
    try:
        r = sb.table("users").select("name,total_points").neq("role", "ADMIN").order("total_points", desc=True).limit(10).execute()
        return r.data or []
    except: return []

async def activate_premium_for(tg_id: int, days: int, plan: str) -> bool:
    try:
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        sb.table("premium_users").upsert({
            "user_id": uid(tg_id), "plan": plan,
            "activated_at": datetime.now().isoformat(),
            "expires_at": expires,
        }, on_conflict="user_id").execute()
        return True
    except: return False

async def save_test_result(tg_id: int, quiz: dict) -> bool:
    try:
        qs = quiz["qs"]
        correct = quiz["correct"]
        total = len(qs)
        score = round(correct / total * 100) if total else 0
        elapsed = int((datetime.now() - datetime.fromisoformat(quiz["started"])).total_seconds())
        details = [{
            "questionId": q["id"],
            "userAnswer": quiz["answers"].get(q["id"], ""),
            "correctAnswer": q["correct_answer"],
            "isCorrect": quiz["answers"].get(q["id"], "") == q["correct_answer"],
        } for q in qs]

        sb.table("test_results").insert({
            "id": f"tg_{tg_id}_{int(datetime.now().timestamp())}",
            "user_id": uid(tg_id),
            "date": datetime.now().isoformat(),
            "total_questions": total,
            "correct_count": correct,
            "score_percentage": score,
            "time_spent_seconds": elapsed,
            "details": details,
        }).execute()

        ur = sb.table("users").select("total_points").eq("id", uid(tg_id)).single().execute()
        if ur.data:
            sb.table("users").update({"total_points": (ur.data.get("total_points") or 0) + score}).eq("id", uid(tg_id)).execute()
        return True
    except: return False

# ╔══════════════════════════════════════════════╗
# ║               KEYBOARDS                       ║
# ╚══════════════════════════════════════════════╝
def kb_main(is_admin=False):
    rows = [
        [KeyboardButton("🚗 Test boshlash"),      KeyboardButton("📚 Kategoriyalar")],
        [KeyboardButton("📊 Natijalarim"),         KeyboardButton("🏆 Reyting")],
        [KeyboardButton("⭐ Premium"),             KeyboardButton("🌐 Sayt")],
        [KeyboardButton("💬 Yordam / Support")],
    ]
    if is_admin:
        rows.append([KeyboardButton("🔑 Admin Panel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def kb_categories():
    cats = [
        ("📚 Umumiy",           "umumiy"),
        ("🚦 Yo'l belgilari",   "belgilar"),
        ("📖 Qoidalar",         "qoidalar"),
        ("🛡 Xavfsizlik",       "xavfsizlik"),
        ("🔧 Texnik holat",     "texnik"),
        ("❤️ Birinchi yordam",  "birinchi-yordam"),
        ("⚠️ Jarimalar",        "jarimalar"),
    ]
    btns = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(name, callback_data=f"cat:{code}") for name, code in cats[i:i+2]]
        btns.append(row)
    btns.append([InlineKeyboardButton("🔙 Orqaga", callback_data="nav:back")])
    return InlineKeyboardMarkup(btns)

def kb_count(cat="all"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10 ta 🏃",  callback_data=f"go:{cat}:10"),
            InlineKeyboardButton("20 ta 🎯",  callback_data=f"go:{cat}:20"),
        ],
        [
            InlineKeyboardButton("30 ta 💪",  callback_data=f"go:{cat}:30"),
            InlineKeyboardButton("40 ta 🔥",  callback_data=f"go:{cat}:40"),
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="nav:cats")],
    ])

def kb_answer(options: dict, qid: str):
    labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
    btns = []
    for k, v in options.items():
        if not v: continue
        short = (v[:40] + "...") if len(v) > 40 else v
        btns.append([InlineKeyboardButton(f"{labels[k]}. {short}", callback_data=f"ans:{qid}:{k}")])
    return InlineKeyboardMarkup(btns)

def kb_next_or_finish(is_last: bool):
    if is_last:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🏁 Natijani ko'rish", callback_data="quiz:finish")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Keyingi savol", callback_data="quiz:next")]])

def kb_premium_plans(prices: dict):
    p1 = int(prices.get("price_1_hafta", 15000))
    p2 = int(prices.get("price_1_oy", 49000))
    p3 = int(prices.get("price_1_yil", 149000))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 1 Hafta - {p1:,} so'm", callback_data="buy:hafta")],
        [InlineKeyboardButton(f"🔥 1 Oy - {p2:,} so'm  ← ENG MASHHUR", callback_data="buy:oy")],
        [InlineKeyboardButton(f"💎 1 Yil - {p3:,} so'm  ← ENG TEJAMKOR", callback_data="buy:yil")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="nav:back")],
    ])

def kb_admin_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏳ So'rovlar",     callback_data="adm:pending"),
            InlineKeyboardButton("📊 Statistika",    callback_data="adm:stats"),
        ],
        [
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm:users"),
            InlineKeyboardButton("🏆 Reyting",          callback_data="adm:top"),
        ],
        [InlineKeyboardButton("📢 Broadcast xabar",  callback_data="adm:broadcast")],
        [InlineKeyboardButton("👑 Premium berish",    callback_data="adm:give")],
    ])

def kb_approve_reject(req_id: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{req_id}"),
        InlineKeyboardButton("❌ Rad etish",  callback_data=f"reject:{req_id}"),
    ]])

# ╔══════════════════════════════════════════════╗
# ║                FORMATTERS                     ║
# ╚══════════════════════════════════════════════╝
def progress_bar(val: int, total: int, width=10) -> str:
    if not total: return "░" * width
    filled = round(val / total * width)
    return "█" * filled + "░" * (width - filled)

def score_badge(score: int) -> str:
    if score >= 95: return "🥇 A+"
    if score >= 85: return "✅ O'tdi"
    if score >= 70: return "👍 Yaxshi"
    if score >= 50: return "😐 O'rta"
    return "❌ O'tmadi"

def fmt_time(sec: int) -> str:
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h: return f"{h}s {m}d"
    if m: return f"{m}d {s}s"
    return f"{s}s"

def rank_medal(i: int) -> str:
    return ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"][i] if i < 10 else "▪️"

def motivational(score: int) -> str:
    if score >= 95: return "🎊 Ajoyib! Imtihondan 100% o'tasiz!"
    if score >= 85: return "🎉 Zo'r! GAI imtihonini bemalol topshirasiz!"
    if score >= 70: return "💪 Yaxshi harakat! Yana bir oz o'qing."
    if score >= 50: return "📚 O'rtacha. Ko'proq mashq qiling!"
    return "😔 Kuchsiz natija. YHQ ni qayta o'qing va mashq qiling."

# ╔══════════════════════════════════════════════╗
# ║                 /START                        ║
# ╚══════════════════════════════════════════════╝
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await ensure_user(update)
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)
    pinfo = await get_premium_info(u.id) if prem else {}

    limit_text = "♾️ Cheksiz" if prem else f"{FREE_LIMIT - used}/{FREE_LIMIT} ta"
    badge = f"👑 *PREMIUM* - {pinfo.get('days_left', 0)} kun qoldi" if prem else "🆓 Bepul foydalanuvchi"

    text = (
        f"🚗 *AvtoTest.Uz*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Salom, *{u.first_name}*! {badge}\n"
        f"📊 Bugungi limit: `{limit_text}`\n\n"
        f"*🎯 Nimalarga ega bo'lasiz:*\n"
        f"✅ 1000+ test savollari (7 ta mavzu)\n"
        f"✅ To'g'ridan bot ichida test ishlash\n"
        f"✅ Har xatoga batafsil izoh\n"
        f"✅ Shaxsiy statistika va tarixingiz\n"
        f"✅ 🏆 Reyting tizimi\n"
        ("✅ 🎬 Video kurslar (20 ta dars)" if prem else "🔒 Video kurslar - Premium") + "\n" +
        ("✅ 📖 YHQ barcha 29 bob" if prem else "🔒 YHQ toliq - Premium") + "\n\n" +
        f"👇 Boshlang!"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=kb_main(u.id == ADMIN_ID)
    )

# ╔══════════════════════════════════════════════╗
# ║               TEST BOSHLASH                   ║
# ╚══════════════════════════════════════════════╝
async def test_start_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)

    if not prem and used >= FREE_LIMIT:
        prices = await get_settings("price_1_hafta", "price_1_oy", "price_1_yil")
        await update.message.reply_text(
            f"⛔ *Kunlik limit tugadi!*\n\n"
            f"📊 Bugun: *{used}/{FREE_LIMIT}* ta test ishlash\n"
            f"🕐 Ertaga yangilanadi: *{(date.today() + timedelta(days=1)).strftime('%d.%m.%Y')}*\n\n"
            f"👑 *Premium bilan CHEKSIZ ishlang:*\n"
            f"♾️ Kunlik limit yo'q\n"
            f"🎬 20 ta video dars\n"
            f"📖 YHQ barcha boblari\n"
            f"🔍 Har xatoga izoh\n\n"
            f"💰 *Qulay narxlar:*",
            parse_mode="Markdown",
            reply_markup=kb_premium_plans(prices)
        )
        return

    remaining = "♾️ Cheksiz" if prem else f"{FREE_LIMIT - used} ta qoldi"
    await update.message.reply_text(
        f"🚗 *Test boshlash*\n\n"
        f"📊 Qolgan limit: *{remaining}*\n\n"
        f"⚡ Nechta savol ishlashni xohlaysiz?",
        parse_mode="Markdown",
        reply_markup=kb_count()
    )

# ╔══════════════════════════════════════════════╗
# ║               KATEGORIYALAR                   ║
# ╚══════════════════════════════════════════════╝
async def categories_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📚 *Kategoriya bo'yicha test*\n\n"
        f"Qaysi mavzuda mashq qilmoqchisiz?\n"
        f"Zaif tomonlaringizni mustahkamlang!",
        parse_mode="Markdown",
        reply_markup=kb_categories()
    )

# ╔══════════════════════════════════════════════╗
# ║               NATIJALAR                       ║
# ╚══════════════════════════════════════════════╝
async def stats_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    s = await get_user_stats(u.id)

    if not s.get("total"):
        await update.message.reply_text(
            f"📊 *Statistika*\n\n"
            f"Hali birorta test topshirmadingiz!\n\n"
            f"🚗 Birinchi testni boshlang va natijalaringiz shu yerda ko'rinadi.",
            parse_mode="Markdown"
        )
        return

    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)
    badge = "👑 Premium" if prem else "🆓 Bepul"
    limit_txt = "♾️" if prem else f"{FREE_LIMIT-used}/{FREE_LIMIT}"

    h, r = divmod(s["time"], 3600)
    m = r // 60
    bar_avg = progress_bar(s["avg"], 100)
    streak = s.get("streak", 0)
    streak_txt = f"\n🔥 *{streak} kunlik seriya!* Davom eting!" if streak > 1 else ""

    text = (
        f"📊 *{u.first_name} - Natijalarim*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{badge}  |  Limit: `{limit_txt}`{streak_txt}\n\n"
        f"*📈 Umumiy:*\n"
        f"🧪 Jami testlar:      *{s['total']}* ta\n"
        f"✅ O'tdi (≥85%):      *{s['passed']}* ta\n"
        f"❌ O'tmadi:           *{s['failed']}* ta\n"
        f"📉 O'tish darajasi:   *{s['pass_rate']}%*\n\n"
        f"*🎯 Balllar:*\n"
        f"📈 O'rtacha:  *{s['avg']}%*\n"
        f"`{bar_avg}`\n"
        f"🏆 Eng yuqori: *{s['best']}%*\n"
        f"📉 Eng past:   *{s['worst']}%*\n"
        f"⭐ Jami ball:  *{s['points']}*\n\n"
        f"*⏱ Sarflangan vaqt:* {h}s {m}d\n\n"
        f"*🕐 Oxirgi 3 test:*\n"
    )
    for res in s.get("recent", []):
        d = res["date"][:10]
        sc = res["score_percentage"]
        tq = res["total_questions"]
        cc = res["correct_count"]
        em = "✅" if sc >= PASS_SCORE else "❌"
        text += f"{em} *{sc}%* - {cc}/{tq} savol • {d}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ╔══════════════════════════════════════════════╗
# ║               REYTING                        ║
# ╚══════════════════════════════════════════════╝
async def leaderboard_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = await get_leaderboard()
    u = update.effective_user

    if not top:
        await update.message.reply_text("🏆 Reyting hali shakillanmagan!\n\nBirinchi bo'ling! 🚀")
        return

    text = f"🏆 *Top-{len(top)} Reyting*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    my_rank = None
    for i, row in enumerate(top):
        name = (row.get("name") or "Noma'lum")[:18]
        pts = row.get("total_points", 0)
        em = rank_medal(i)
        is_me = row.get("id") == uid(u.id)
        line = f"{em} *{name}* - {pts} ball"
        if is_me:
            line += " ← Siz"
            my_rank = i + 1
        text += line + "\n"

    if my_rank:
        text += f"\n━━━━━━━━━━━━━━━━━━━━━━\n👤 Sizning o'rningiz: *#{my_rank}*"
    else:
        text += f"\n━━━━━━━━━━━━━━━━━━━━━━\n👤 Siz hali reyting top-10 da emassiz"

    await update.message.reply_text(text, parse_mode="Markdown")

# ╔══════════════════════════════════════════════╗
# ║               PREMIUM                        ║
# ╚══════════════════════════════════════════════╝
async def premium_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    pinfo = await get_premium_info(u.id)

    if pinfo.get("active"):
        text = (
            f"👑 *Premium - Faol!*\n\n"
            f"📦 Tarif: *{pinfo['plan']}*\n"
            f"📅 Tugash sanasi: *{pinfo['expires']}*\n"
            f"⏳ Qoldi: *{pinfo['days_left']} kun*\n\n"
            f"*Sizda mavjud:*\n"
            f"✅ Cheksiz kunlik testlar\n"
            f"✅ 20 ta video dars (Kurslar)\n"
            f"✅ YHQ kitob - barcha 29 bob\n"
            f"✅ Har xatoga batafsil izoh\n"
            f"✅ Reyting imtiyozlari\n\n"
            f"🚗 Saytda ham barcha imkoniyatlar ochiq!"
        )
        await update.message.reply_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌐 Saytni ochish", web_app=WebAppInfo(url=WEBAPP_URL))
            ]]))
        return

    prices = await get_settings("price_1_hafta", "price_1_oy", "price_1_yil")
    p1 = int(prices.get("price_1_hafta", 15000))
    p2 = int(prices.get("price_1_oy", 49000))
    p3 = int(prices.get("price_1_yil", 149000))

    text = (
        f"⭐ *Premium Obuna*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Premium bilan nima olasiz?*\n\n"
        f"♾️  Cheksiz kunlik testlar\n"
        f"🎬  20 ta video dars (Kurslar bo'limi)\n"
        f"📖  YHQ kitob - barcha 29 bob\n"
        f"🔍  Har xatoga batafsil izoh va tushuntirish\n"
        f"🏆  Reytingda premium nishon\n"
        f"📊  Kengaytirilgan statistika\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Narxlar:*\n\n"
        f"📅  1 Hafta - *{p1:,} so'm*\n"
        f"🔥  1 Oy    - *{p2:,} so'm*   ← Ko'pchilik tanlaydi\n"
        f"💎  1 Yil   - *{p3:,} so'm*   ← Eng tejamkor\n\n"
        f"👇 Tarif tanlang:"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=kb_premium_plans(prices))

# ╔══════════════════════════════════════════════╗
# ║            SAYT (WebApp)                      ║
# ╚══════════════════════════════════════════════╝
async def site_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    prem = await is_premium(update.effective_user.id)
    text = (
        f"🌐 *AvtoTest.Uz - To'liq Platforma*\n\n"
        f"Saytda qo'shimcha imkoniyatlar:\n"
        f"{'✅' if prem else '🔒'} Video kurslar (20 ta dars)\n"
        f"{'✅' if prem else '🔒'} YHQ - barcha 29 bob\n"
        f"✅ Test tarixingiz\n"
        f"✅ Premium boshqaruv\n\n"
        f"👇 Ochish:"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Saytni ochish", web_app=WebAppInfo(url=WEBAPP_URL))
        ]]))

# ╔══════════════════════════════════════════════╗
# ║        SUPPORT (ConversationHandler)          ║
# ╚══════════════════════════════════════════════╝
async def support_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💬 *Yordam / Support*\n\n"
        f"Savolingiz yoki muammoingizni yozing.\n"
        f"Admin 1-24 soat ichida javob beradi!\n\n"
        f"📌 To'g'ridan ham yozishingiz mumkin: @kamron201\n\n"
        f"❌ Bekor qilish: /cancel",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return SUPPORT_WAIT

async def support_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    text = update.message.text
    prem = await is_premium(u.id)
    badge = "👑 PREMIUM" if prem else "🆓 Bepul"
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"📩 *Yangi support xabari!*\n\n"
            f"👤 [{u.first_name}](tg://user?id={u.id})\n"
            f"🏷 {badge}  |  🆔 `{u.id}`\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"💬 *Xabar:*\n{text}\n\n"
            f"📌 Javob berish: tg://user?id={u.id}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Javob berish", url=f"tg://user?id={u.id}")
            ]])
        )
    except: pass
    await update.message.reply_text(
        "✅ *Xabaringiz yuborildi!*\n\nAdmin tez orada javob beradi.",
        parse_mode="Markdown",
        reply_markup=kb_main(u.id == ADMIN_ID)
    )
    return ConversationHandler.END

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Bekor qilindi.",
        reply_markup=kb_main(update.effective_user.id == ADMIN_ID)
    )
    return ConversationHandler.END

# ╔══════════════════════════════════════════════╗
# ║            ADMIN PANEL                        ║
# ╚══════════════════════════════════════════════╝
async def admin_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Ruxsat yo'q!")
        return
    await _send_admin_panel(update.message.reply_text)

async def _send_admin_panel(send_fn):
    try:
        ur = sb.table("users").select("id", count="exact").neq("role","ADMIN").execute()
        qr = sb.table("questions").select("id", count="exact").execute()
        tr = sb.table("test_results").select("id", count="exact").execute()
        pr = sb.table("premium_users").select("id", count="exact").gt("expires_at", datetime.now().isoformat()).execute()
        pnd = sb.table("premium_requests").select("id", count="exact").eq("status","pending").execute()
        total_u = ur.count or 0
        total_q = qr.count or 0
        total_t = tr.count or 0
        active_p = pr.count or 0
        pending = pnd.count or 0
    except:
        total_u = total_q = total_t = active_p = pending = 0

    text = (
        f"🔑 *Admin Panel*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Foydalanuvchilar: *{total_u}*\n"
        f"📝 Savollar: *{total_q}*\n"
        f"🧪 Jami testlar: *{total_t}*\n"
        f"👑 Aktiv Premium: *{active_p}*\n"
        f"⏳ Kutilayotgan so'rovlar: *{pending}*\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        ("🔴 *" + str(pending) + " ta yangi sorov bor!*" if pending else "✅ Yangi sorovlar yoq")
    )
    await send_fn(text, parse_mode="Markdown", reply_markup=kb_admin_main())

# ╔══════════════════════════════════════════════╗
# ║              QUIZ ENGINE                      ║
# ╚══════════════════════════════════════════════╝
async def launch_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cat: str, count: int):
    u = update.effective_user
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)

    if not prem and used >= FREE_LIMIT:
        prices = await get_settings("price_1_hafta", "price_1_oy", "price_1_yil")
        await update.effective_message.edit_text(
            f"⛔ *Kunlik limit tugadi!*\n\nBugun {FREE_LIMIT} ta test ishladingiz.\nPremium bilan cheksiz!",
            parse_mode="Markdown", reply_markup=kb_premium_plans(prices)
        )
        return

    qs = await fetch_questions(count, cat)
    if not qs:
        await update.effective_message.edit_text(
            "❌ Bu kategoriyada savollar topilmadi. Boshqa kategoriya tanlang.")
        return

    ctx.user_data["quiz"] = {
        "qs": qs, "idx": 0, "answers": {}, "correct": 0,
        "cat": cat, "started": datetime.now().isoformat(),
    }
    try:
        await update.effective_message.delete()
    except: pass
    await _send_quiz_question(update.effective_chat.id, ctx)

async def _send_quiz_question(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE):
    quiz = ctx.user_data.get("quiz")
    if not quiz: return

    q = quiz["qs"][quiz["idx"]]
    idx = quiz["idx"]
    total = len(quiz["qs"])
    bar = progress_bar(idx, total)
    labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}

    opts = {k: q.get(f"option_{k.lower()}", "") for k in ("A","B","C","D")}
    if q.get("option_e"): opts["E"] = q["option_e"]
    opts = {k: v for k, v in opts.items() if v}

    opts_lines = "\n".join([f"  *{labels[k]}.* {v}" for k, v in opts.items()])

    text = (
        f"❓ *Savol {idx+1}/{total}*\n"
        f"`{bar}` {idx+1}/{total}\n"
        f"✅ {quiz['correct']} to'g'ri | ❌ {idx - quiz['correct']} xato\n\n"
        f"*{q['question_text']}*\n\n"
        f"{opts_lines}"
    )
    kb = kb_answer(opts, q["id"])

    if q.get("image"):
        try:
            await ctx.bot.send_photo(chat_id, q["image"], caption=text,
                                     parse_mode="Markdown", reply_markup=kb)
            return
        except: pass
    await ctx.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

async def _finish_quiz(chat_id: int, u, ctx: ContextTypes.DEFAULT_TYPE):
    quiz = ctx.user_data.pop("quiz", None)
    if not quiz: return

    total = len(quiz["qs"])
    correct = quiz["correct"]
    score = round(correct / total * 100) if total else 0
    passed = score >= PASS_SCORE
    elapsed = int((datetime.now() - datetime.fromisoformat(quiz["started"])).total_seconds())

    await save_test_result(u.id, quiz)
    await increment_daily(u.id)

    # Xato savollar ro'yxati (max 5 ta)
    wrong_qs = [q for q in quiz["qs"] if quiz["answers"].get(q["id"],"") != q["correct_answer"]]
    wrong_text = ""
    if wrong_qs and not passed:
        labels = {"A":"F1","B":"F2","C":"F3","D":"F4","E":"F5"}
        wrong_text = "\n\n*❌ Xato javoblar:*\n"
        for wq in wrong_qs[:5]:
            rk = wq["correct_answer"]
            rv = wq.get(f"option_{rk.lower()}", "")
            q_short = wq["question_text"][:55] + ("..." if len(wq["question_text"]) > 55 else "")
            wrong_text += f"▪️ _{q_short}_\n   ✅ {labels[rk]}. {rv[:45]}\n"
        if len(wrong_qs) > 5:
            wrong_text += f"_...va yana {len(wrong_qs)-5} ta xato_\n"

    bar = progress_bar(score, 100, 10)
    badge = score_badge(score)
    motiv = motivational(score)

    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)
    limit_txt = "♾️ Cheksiz" if prem else f"{FREE_LIMIT-used}/{FREE_LIMIT}"

    text = (
        f"{'🎉' if passed else '📊'} *Test yakunlandi!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*{badge}*\n\n"
        f"📊 Natija:   *{correct}/{total}* to'g'ri\n"
        f"📈 Ball:     *{score}%*\n"
        f"`{bar}`\n"
        f"⏱ Vaqt:    *{fmt_time(elapsed)}*\n\n"
        f"💬 _{motiv}_\n"
        f"📋 Limit: `{limit_txt}`"
        f"{wrong_text}"
    )

    btns = [
        [
            InlineKeyboardButton("🔄 Qayta", callback_data=f"go:{quiz['cat']}:{total}"),
            InlineKeyboardButton("📊 Statistika", callback_data="nav:stats"),
        ],
    ]
    if not prem:
        btns.append([InlineKeyboardButton("⭐ Premium - Cheksiz test!", callback_data="nav:premium")])
    btns.append([InlineKeyboardButton("🏠 Bosh menu", callback_data="nav:back")])

    await ctx.bot.send_message(chat_id, text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(btns))

# ╔══════════════════════════════════════════════╗
# ║          CALLBACK QUERY HANDLER               ║
# ╚══════════════════════════════════════════════╝
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    u = q.from_user
    chat_id = update.effective_chat.id

    # ── Kategoriya tanlash ──
    if d.startswith("cat:"):
        cat = d[4:]
        cat_names = {
            "umumiy": "📚 Umumiy", "belgilar": "🚦 Yo'l belgilari",
            "qoidalar": "📖 Qoidalar", "xavfsizlik": "🛡Xavfsizlik",
            "texnik": "🔧 Texnik holat", "birinchi-yordam": "❤️ Birinchi yordam",
            "jarimalar": "⚠️ Jarimalar",
        }
        prem = await is_premium(u.id)
        used = await get_daily_used(u.id)
        remaining = "♾️" if prem else f"{FREE_LIMIT - used} ta"
        await q.edit_message_text(
            f"*{cat_names.get(cat, cat)}*\n\n"
            f"📊 Qolgan limit: *{remaining}*\n\n"
            f"Nechta savol?",
            parse_mode="Markdown",
            reply_markup=kb_count(cat)
        )

    # ── Test boshlash ──
    elif d.startswith("go:"):
        _, cat, cnt = d.split(":")
        await launch_quiz(update, ctx, cat, int(cnt))

    # ── Javob berish ──
    elif d.startswith("ans:"):
        _, qid, ans = d.split(":", 2)
        quiz = ctx.user_data.get("quiz")
        if not quiz or qid in quiz["answers"]: return

        cq = quiz["qs"][quiz["idx"]]
        if cq["id"] != qid: return

        quiz["answers"][qid] = ans
        is_right = ans == cq["correct_answer"]
        if is_right: quiz["correct"] += 1

        labels = {"A":"F1","B":"F2","C":"F3","D":"F4","E":"F5"}
        opts = {k: cq.get(f"option_{k.lower()}", "") for k in "ABCDE"}
        opts = {k: v for k, v in opts.items() if v}

        right_key = cq["correct_answer"]
        right_val = opts.get(right_key, "")
        user_val  = opts.get(ans, "")

        if is_right:
            result_text = f"✅ *To'g'ri!*\n{labels[ans]}. {user_val}"
        else:
            result_text = (
                f"❌ *Noto'g'ri!*\n"
                f"Siz: {labels[ans]}. {user_val}\n\n"
                f"✅ *To'g'ri javob:*\n{labels[right_key]}. {right_val}"
            )

        desc = cq.get("description", "")
        if desc:
            result_text += f"\n\n💡 *Izoh:*\n_{desc}_"

        is_last = quiz["idx"] >= len(quiz["qs"]) - 1
        result_text += f"\n\n📊 {quiz['correct']}/{quiz['idx']+1} to'g'ri"

        try:
            await q.edit_message_caption(
                result_text, parse_mode="Markdown",
                reply_markup=kb_next_or_finish(is_last)
            )
        except:
            try:
                await q.edit_message_text(
                    result_text, parse_mode="Markdown",
                    reply_markup=kb_next_or_finish(is_last)
                )
            except: pass

    # ── Keyingi savol ──
    elif d == "quiz:next":
        quiz = ctx.user_data.get("quiz")
        if not quiz: return
        quiz["idx"] += 1
        if quiz["idx"] >= len(quiz["qs"]):
            try: await q.delete_message()
            except: pass
            await _finish_quiz(chat_id, u, ctx)
        else:
            try: await q.delete_message()
            except: pass
            await _send_quiz_question(chat_id, ctx)

    # ── Test yakunlash ──
    elif d == "quiz:finish":
        try: await q.delete_message()
        except: pass
        await _finish_quiz(chat_id, u, ctx)

    # ── Premium xarid ──
    elif d.startswith("buy:"):
        plan_key = d[4:]
        plans = {
            "hafta": ("1 Hafta",  7,   "price_1_hafta", "📅"),
            "oy":    ("1 Oy",    30,   "price_1_oy",    "🔥"),
            "yil":   ("1 Yil",  365,   "price_1_yil",   "💎"),
        }
        pname, days, pkey, em = plans[plan_key]
        price = int(await get_setting(pkey, "49000"))
        s = await get_settings("card_number","card_owner","card_type")
        card_num = s.get("card_number", "0000 0000 0000 0000")
        card_own = s.get("card_owner", "Admin")
        card_typ = s.get("card_type", "Humo")

        await q.edit_message_text(
            f"{em} *{pname} Premium - {price:,} so'm*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*💳 To'lov rekvizitlari:*\n"
            f"🔢 Karta:   `{card_num}`\n"
            f"👤 Egasi:   {card_own}\n"
            f"🏦 Turi:    {card_typ}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*📌 Qadamlar:*\n"
            f"1️⃣ *{price:,} so'm* kartaga o'tkazing\n"
            f"2️⃣ To'lov chekini screenshot oling\n"
            f"3️⃣ @kamron201 ga chekni yuboring\n"
            f"4️⃣ Admin *{days} kunlik* Premiumni faollashtiradi\n\n"
            f"⏱ Odatdagi tasdiqlash vaqti: *1-3 soat*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Chekni yuborish → @kamron201", url="https://t.me/kamron201")],
                [InlineKeyboardButton("🔙 Boshqa tarif", callback_data="nav:premium")],
            ])
        )

    # ── Navigatsiya ──
    elif d.startswith("nav:"):
        dest = d[4:]
        if dest == "back":
            try: await q.delete_message()
            except: pass
        elif dest == "cats":
            await q.edit_message_text(
                "📚 *Kategoriya bo'yicha test*\n\nQaysi mavzuda mashq qilmoqchisiz?",
                parse_mode="Markdown", reply_markup=kb_categories()
            )
        elif dest == "premium":
            prices = await get_settings("price_1_hafta","price_1_oy","price_1_yil")
            p2 = int(prices.get("price_1_oy", 49000))
            await q.edit_message_text(
                f"⭐ *Premium Obuna*\n\n♾️ Cheksiz testlar\n🎬 Video kurslar\n📖 YHQ kitob\n\n💰 1 Oy - *{p2:,} so'm* 🔥\n\n👇 Tarif tanlang:",
                parse_mode="Markdown", reply_markup=kb_premium_plans(prices)
            )
        elif dest == "stats":
            try: await q.delete_message()
            except: pass
            s = await get_user_stats(u.id)
            text = (
                f"📊 *Natijalarim*\n\n"
                f"🧪 Jami: *{s.get('total',0)}* test\n"
                f"✅ O'tdi: *{s.get('passed',0)}* ta\n"
                f"📈 O'rtacha: *{s.get('avg',0)}%*\n"
                f"🏆 Eng yaxshi: *{s.get('best',0)}%*"
            )
            await ctx.bot.send_message(chat_id, text, parse_mode="Markdown")

    # ── Admin callbacks ──
    elif d.startswith("adm:") and u.id == ADMIN_ID:
        sub = d[4:]

        if sub == "stats":
            try:
                ur = sb.table("users").select("id",count="exact").neq("role","ADMIN").execute()
                qr = sb.table("questions").select("id",count="exact").execute()
                tr = sb.table("test_results").select("id",count="exact").execute()
                pr = sb.table("premium_users").select("id",count="exact").gt("expires_at", datetime.now().isoformat()).execute()
                pnd = sb.table("premium_requests").select("id",count="exact").eq("status","pending").execute()
                # Bugun register bo'lganlar
                today = date.today().isoformat()
                new_today = sb.table("users").select("id",count="exact").gte("created_at", today).neq("role","ADMIN").execute()
            except:
                class _Z:
                    count = 0
                ur=qr=tr=pr=pnd=new_today=_Z()

            text = (
                f"📊 *Admin - Statistika*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Jami foydalanuvchilar: *{ur.count}*\n"
                f"🆕 Bugun qo'shildi: *{new_today.count}*\n"
                f"📝 Savollar soni: *{qr.count}*\n"
                f"🧪 Jami testlar: *{tr.count}*\n"
                f"👑 Aktiv Premium: *{pr.count}*\n"
                f"⏳ Kutilayotgan: *{pnd.count}*\n\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            await q.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga",callback_data="adm:back")]]))

        elif sub == "top":
            top = await get_leaderboard()
            text = f"🏆 *Top-10 Reyting*\n{'━'*22}\n\n"
            for i, row in enumerate(top):
                text += f"{rank_medal(i)} {(row.get('name') or '?')[:18]} - *{row.get('total_points',0)}* ball\n"
            await q.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙",callback_data="adm:back")]]))

        elif sub == "users":
            try:
                users = sb.table("users").select("name,created_at,last_active").neq("role","ADMIN").order("created_at",desc=True).limit(10).execute().data or []
            except: users = []
            text = f"👥 *So'nggi 10 foydalanuvchi*\n{'━'*22}\n\n"
            for r in users:
                la = r.get("last_active","")[:10]
                text += f"👤 {(r.get('name') or '?')[:20]} | {r.get('created_at','')[:10]} | Faol: {la}\n"
            await q.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙",callback_data="adm:back")]]))

        elif sub == "pending":
            try:
                reqs = sb.table("premium_requests").select("*").eq("status","pending").order("created_at",desc=True).limit(10).execute().data or []
            except: reqs = []
            if not reqs:
                await q.edit_message_text("✅ Kutilayotgan so'rovlar yo'q!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙",callback_data="adm:back")]]))
                return
            await q.edit_message_text(f"⏳ *{len(reqs)} ta so'rov* yuborilmoqda...", parse_mode="Markdown")
            for req in reqs:
                req_text = (
                    f"📋 *Premium So'rov*\n\n"
                    f"👤 *{req.get('user_name','?')}*\n"
                    f"📦 Tarif: *{req.get('plan','')}*\n"
                    f"💰 Narx: *{req.get('price',0):,} so'm*\n"
                    f"📅 {(req.get('created_at') or '')[:16].replace('T',' ')}"
                )
                ss = req.get("screenshot_url","")
                try:
                    if ss:
                        await ctx.bot.send_photo(ADMIN_ID, ss, caption=req_text,
                            parse_mode="Markdown", reply_markup=kb_approve_reject(req["id"]))
                    else:
                        await ctx.bot.send_message(ADMIN_ID, req_text,
                            parse_mode="Markdown", reply_markup=kb_approve_reject(req["id"]))
                except: pass

        elif sub == "broadcast":
            ctx.user_data["adm_await"] = "broadcast"
            await q.edit_message_text(
                "📢 *Broadcast*\n\nBarcha foydalanuvchilarga yuboriladi.\n\n✏️ Xabar matnini yozing:\n_(Bekor: /cancel)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="adm:back")]]))

        elif sub == "give":
            ctx.user_data["adm_await"] = "give_id"
            await q.edit_message_text(
                "👑 *Premium berish*\n\n"
                "Foydalanuvchi Telegram ID sini yozing:\n_(masalan: `123456789`)_\n\n_(Bekor: /cancel)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="adm:back")]]))

        elif sub == "back":
            await _send_admin_panel(q.edit_message_text)

    # ── Approve / Reject ──
    elif d.startswith("approve:") and u.id == ADMIN_ID:
        req_id = d[8:]
        try:
            req = sb.table("premium_requests").select("*").eq("id", req_id).single().execute().data
            if not req:
                await q.edit_message_text("❌ So'rov topilmadi!"); return

            days = req.get("days", 30)
            tg_id_str = req["user_id"].replace("user_","").split("_")[0]
            tg_id_int = int(tg_id_str)

            ok = await activate_premium_for(tg_id_int, days, req.get("plan","Premium"))
            sb.table("premium_requests").update({"status":"approved"}).eq("id",req_id).execute()

            if ok:
                pinfo = await get_premium_info(tg_id_int)
                try:
                    await ctx.bot.send_message(
                        tg_id_int,
                        f"🎉 *Premium faollashdi!*\n\n"
                        f"👑 Tarif: *{req.get('plan','Premium')}*\n"
                        f"📅 Tugash sanasi: *{pinfo.get('expires','?')}*\n"
                        f"⏳ Kunlar: *{days}*\n\n"
                        f"✅ Cheksiz testlar\n"
                        f"✅ 20 ta video dars\n"
                        f"✅ YHQ barcha boblari\n\n"
                        f"Xaridingiz uchun rahmat! 🚗\n"
                        f"Sayt: {WEBAPP_URL}",
                        parse_mode="Markdown"
                    )
                except: pass
                await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"✅ Tasdiqlangan - {req.get('user_name','?')}", callback_data="noop")]
                ]))
            else:
                await q.edit_message_text("❌ Faollashtrishda xato!")
        except Exception as e:
            await q.edit_message_text(f"❌ Xato: {e}")

    elif d.startswith("reject:") and u.id == ADMIN_ID:
        req_id = d[7:]
        try:
            req = sb.table("premium_requests").select("*").eq("id",req_id).single().execute().data
            if req:
                sb.table("premium_requests").update({"status":"rejected"}).eq("id",req_id).execute()
                tg_id_str = req["user_id"].replace("user_","").split("_")[0]
                try:
                    await ctx.bot.send_message(int(tg_id_str),
                        f"❌ *Premium so'rovingiz rad etildi*\n\n"
                        f"To'lov tasdiqlanmadi.\n"
                        f"Muammo bo'lsa @kamron201 ga yozing.",
                        parse_mode="Markdown")
                except: pass
                await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"❌ Rad etildi - {req.get('user_name','?')}", callback_data="noop")]
                ]))
        except Exception as e:
            await q.edit_message_text(f"❌ Xato: {e}")

# ╔══════════════════════════════════════════════╗
# ║         ADMIN TEXT HANDLER                    ║
# ╚══════════════════════════════════════════════╝
async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user.id != ADMIN_ID: return False
    action = ctx.user_data.get("adm_await")
    if not action: return False

    text = update.message.text
    ctx.user_data.pop("adm_await", None)

    # Broadcast
    if action == "broadcast":
        try:
            users = sb.table("users").select("id").neq("role","ADMIN").execute().data or []
        except: users = []
        await update.message.reply_text(f"📢 Yuborilmoqda... ({len(users)} ta foydalanuvchi)")
        sent = failed = 0
        for row in users:
            try:
                tg_id = int(row["id"].replace("user_","").split("_")[0])
                await ctx.bot.send_message(
                    tg_id,
                    f"📢 *AvtoTest.Uz - Yangilik!*\n\n{text}\n\n🌐 {WEBAPP_URL}",
                    parse_mode="Markdown"
                )
                sent += 1
                await asyncio.sleep(0.05)
            except: failed += 1
        await update.message.reply_text(
            f"📢 *Broadcast yakunlandi!*\n\n✅ Yuborildi: *{sent}*\n❌ Xato: *{failed}*",
            parse_mode="Markdown"
        )

    # Premium ID kiritish
    elif action == "give_id":
        try:
            tg_id = int(text.strip())
            ctx.user_data["give_tg_id"] = tg_id
            ctx.user_data["adm_await"] = "give_days"
            await update.message.reply_text(
                f"👤 ID: `{tg_id}` kiritildi.\n\nNecha kunlik Premium berasiz?",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Noto'g'ri ID! Faqat raqam kiriting.")

    # Premium kun kiritish
    elif action == "give_days":
        tg_id = ctx.user_data.pop("give_tg_id", None)
        if not tg_id:
            await update.message.reply_text("❌ Xato. Qaytadan bosing.")
            return True
        try:
            days = int(text.strip())
            ok = await activate_premium_for(tg_id, days, f"Admin sovg'asi ({days} kun)")
            if ok:
                try:
                    await ctx.bot.send_message(
                        tg_id,
                        f"🎁 *Premium sovg'a oldi!*\n\n"
                        f"👑 Admin tomonidan *{days} kunlik* Premium berildi!\n\n"
                        f"✅ Cheksiz testlar\n✅ Video kurslar\n✅ YHQ barcha boblari\n\n"
                        f"Unumli foydalaning! 🚗",
                        parse_mode="Markdown"
                    )
                except: pass
                await update.message.reply_text(
                    f"✅ `{tg_id}` ga *{days} kunlik* Premium berildi!",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Premium berishda xato!")
        except:
            await update.message.reply_text("❌ Noto'g'ri kun soni!")

    return True

# ╔══════════════════════════════════════════════╗
# ║          MESSAGE ROUTER                       ║
# ╚══════════════════════════════════════════════╝
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    text = update.message.text or ""

    if u.id == ADMIN_ID and ctx.user_data.get("adm_await"):
        if await handle_admin_text(update, ctx): return

    await ensure_user(update)
    is_adm = (u.id == ADMIN_ID)

    routes = {
        "🚗 Test boshlash":        test_start_msg,
        "📚 Kategoriyalar":        categories_msg,
        "📊 Natijalarim":          stats_msg,
        "🏆 Reyting":              leaderboard_msg,
        "⭐ Premium":              premium_msg,
        "🌐 Sayt":                 site_msg,
        "🔑 Admin Panel":          admin_msg,
    }
    fn = routes.get(text)
    if fn:
        await fn(update, ctx)
    else:
        await update.message.reply_text(
            "👇 Pastdagi menyudan foydalaning:",
            reply_markup=kb_main(is_adm)
        )

# ╔══════════════════════════════════════════════╗
# ║             COMMANDS                          ║
# ╚══════════════════════════════════════════════╝
async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await test_start_msg(update, ctx)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await stats_msg(update, ctx)

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await leaderboard_msg(update, ctx)

async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await premium_msg(update, ctx)

async def cmd_admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await admin_msg(update, ctx)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 *AvtoTest.Uz Bot v3.0 - Yordam*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*📌 Buyruqlar:*\n"
        f"/start   - Bosh menyu\n"
        f"/test    - Test boshlash\n"
        f"/stats   - Natijalarim\n"
        f"/top     - Reyting\n"
        f"/premium - Premium ma'lumot\n"
        f"/help    - Yordam\n\n"
        f"*📌 Qanday ishlaydi?*\n"
        f"1️⃣ Test boshlang (10/20/30/40 savol)\n"
        f"2️⃣ Har savolga F1-F4 dan javob bering\n"
        f"3️⃣ Har javobdan keyin to'g'ri javob ko'rinadi\n"
        f"4️⃣ Test tugagach batafsil natija chiqadi\n\n"
        f"*📌 Bepul:* kuniga {FREE_LIMIT} ta test\n"
        f"*👑 Premium:* cheksiz + videolar + YHQ\n\n"
        f"❓ Muammo: @kamron201",
        parse_mode="Markdown"
    )

# ╔══════════════════════════════════════════════╗
# ║                  MAIN                         ║
# ╚══════════════════════════════════════════════╝
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Support conversation
    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 Yordam / Support$"), support_entry)],
        states={
            SUPPORT_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("admin", cmd_admin_cmd))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(support_conv)
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("🚗 AvtoTest.Uz Bot v3.0 ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
