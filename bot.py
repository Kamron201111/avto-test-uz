import os
import random
import logging
import asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
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
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "8570122455:AAG63c-ta1bigTRLkaj76GFXiF3a4wiY7IM")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "1935541521"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bwdnvxucvyeknesifnwg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "https://avto-test-uz-three.vercel.app")
FREE_LIMIT   = 20
PASS_SCORE   = 85

# Supabase - faqat key bo'lsa ulanamiz
sb = None
try:
    _key = SUPABASE_KEY.strip() if SUPABASE_KEY else ""
    if _key and len(_key) > 10:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, _key)
        log.info("Supabase ulandi!")
    else:
        log.warning("SUPABASE_KEY yoq yoki qisqa - Railway Variables ga qoshing!")
except Exception as e:
    log.error("Supabase ulanmadi: " + str(e))
    sb = None

SUPPORT_WAIT = 1


# ============================================================
# SUPABASE HELPERS
# ============================================================

def make_uid(tg_id):
    return "user_" + str(tg_id)


async def is_premium(tg_id):
    if not sb:
        return False
    try:
        r = sb.table("premium_users").select("expires_at").eq("user_id", make_uid(tg_id)).single().execute()
        if r.data:
            exp_str = r.data["expires_at"].replace("Z", "+00:00")
            return datetime.fromisoformat(exp_str) > datetime.now().astimezone()
    except:
        pass
    return False


async def get_premium_info(tg_id):
    if not sb:
        return {"active": False, "expires": "", "plan": "", "days_left": 0}
    try:
        r = sb.table("premium_users").select("expires_at,plan").eq("user_id", make_uid(tg_id)).single().execute()
        if r.data:
            exp = datetime.fromisoformat(r.data["expires_at"].replace("Z", "+00:00"))
            days_left = max(0, (exp.date() - date.today()).days)
            return {
                "active": exp > datetime.now().astimezone(),
                "expires": exp.strftime("%d.%m.%Y"),
                "plan": r.data.get("plan", "Premium"),
                "days_left": days_left
            }
    except:
        pass
    return {"active": False, "expires": "", "plan": "", "days_left": 0}


async def get_daily_used(tg_id):
    if not sb:
        return 0
    try:
        today = date.today().isoformat()
        r = sb.table("daily_tests").select("count").eq("user_id", make_uid(tg_id)).eq("test_date", today).single().execute()
        return r.data["count"] if r.data else 0
    except:
        return 0


async def increment_daily(tg_id):
    if not sb:
        return
    try:
        today = date.today().isoformat()
        r = sb.table("daily_tests").select("count").eq("user_id", make_uid(tg_id)).eq("test_date", today).single().execute()
        if r.data:
            sb.table("daily_tests").update({"count": r.data["count"] + 1}).eq("user_id", make_uid(tg_id)).eq("test_date", today).execute()
        else:
            sb.table("daily_tests").insert({"user_id": make_uid(tg_id), "test_date": today, "count": 1}).execute()
    except:
        pass


async def ensure_user(update):
    if not sb:
        return
    u = update.effective_user
    try:
        r = sb.table("users").select("id").eq("id", make_uid(u.id)).single().execute()
        now = datetime.now().isoformat()
        if not r.data:
            full = ((u.first_name or "") + " " + (u.last_name or "")).strip()
            sb.table("users").insert({
                "id": make_uid(u.id),
                "name": u.first_name or u.username or "Foydalanuvchi",
                "full_name": full,
                "role": "USER",
                "total_points": 0,
                "created_at": now,
                "last_active": now,
            }).execute()
        else:
            sb.table("users").update({"last_active": datetime.now().isoformat()}).eq("id", make_uid(u.id)).execute()
    except:
        pass


async def fetch_questions(count, category=None):
    if not sb:
        return []
    try:
        q = sb.table("questions").select("*")
        if category and category != "all":
            q = q.eq("category", category)
        r = q.execute()
        qs = r.data or []
        random.shuffle(qs)
        return qs[:count]
    except:
        return []


async def get_setting(key, default=""):
    if not sb:
        return default
    try:
        r = sb.table("settings").select("value").eq("key", key).single().execute()
        return r.data["value"] if r.data else default
    except:
        return default


async def get_settings_dict(*keys):
    if not sb:
        return {}
    try:
        r = sb.table("settings").select("key,value").in_("key", list(keys)).execute()
        return {row["key"]: row["value"] for row in (r.data or [])}
    except:
        return {}


async def get_user_stats(tg_id):
    if not sb:
        return {"total": 0}
    try:
        r = sb.table("test_results").select("*").eq("user_id", make_uid(tg_id)).order("date", desc=True).limit(100).execute()
        data = r.data or []
        if not data:
            return {"total": 0}
        total = len(data)
        passed = sum(1 for d in data if d["score_percentage"] >= PASS_SCORE)
        avg = round(sum(d["score_percentage"] for d in data) / total)
        best = max(d["score_percentage"] for d in data)
        worst = min(d["score_percentage"] for d in data)
        time_total = sum(d.get("time_spent_seconds", 0) for d in data)
        streak = 0
        used_dates = sorted(set(d["date"][:10] for d in data), reverse=True)
        check = date.today()
        for ds in used_dates:
            if date.fromisoformat(ds) == check:
                streak += 1
                check -= timedelta(days=1)
            else:
                break
        ur = sb.table("users").select("total_points").eq("id", make_uid(tg_id)).single().execute()
        points = ur.data.get("total_points", 0) if ur.data else 0
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "avg": avg,
            "best": best,
            "worst": worst,
            "time": time_total,
            "points": points,
            "streak": streak,
            "pass_rate": round(passed / total * 100),
            "recent": data[:3]
        }
    except:
        return {"total": 0}


async def get_leaderboard():
    if not sb:
        return []
    try:
        r = sb.table("users").select("id,name,total_points").neq("role", "ADMIN").order("total_points", desc=True).limit(10).execute()
        return r.data or []
    except:
        return []


async def activate_premium_for(tg_id, days, plan):
    if not sb:
        return False
    try:
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        sb.table("premium_users").upsert({
            "user_id": make_uid(tg_id),
            "plan": plan,
            "activated_at": datetime.now().isoformat(),
            "expires_at": expires,
        }, on_conflict="user_id").execute()
        return True
    except:
        return False


async def save_result(tg_id, quiz):
    if not sb:
        return
    try:
        qs = quiz["qs"]
        correct = quiz["correct"]
        total = len(qs)
        score = round(correct / total * 100) if total else 0
        elapsed = int((datetime.now() - datetime.fromisoformat(quiz["started"])).total_seconds())
        details = []
        for q in qs:
            ua = quiz["answers"].get(q["id"], "")
            details.append({
                "questionId": q["id"],
                "userAnswer": ua,
                "correctAnswer": q["correct_answer"],
                "isCorrect": ua == q["correct_answer"],
            })
        sb.table("test_results").insert({
            "id": "tg_" + str(tg_id) + "_" + str(int(datetime.now().timestamp())),
            "user_id": make_uid(tg_id),
            "date": datetime.now().isoformat(),
            "total_questions": total,
            "correct_count": correct,
            "score_percentage": score,
            "time_spent_seconds": elapsed,
            "details": details,
        }).execute()
        ur = sb.table("users").select("total_points").eq("id", make_uid(tg_id)).single().execute()
        if ur.data:
            old_pts = ur.data.get("total_points") or 0
            sb.table("users").update({"total_points": old_pts + score}).eq("id", make_uid(tg_id)).execute()
    except:
        pass


# ============================================================
# KEYBOARDS
# ============================================================

def kb_main(is_admin=False):
    rows = [
        [KeyboardButton("Test boshlash"), KeyboardButton("Kategoriyalar")],
        [KeyboardButton("Natijalarim"),   KeyboardButton("Reyting")],
        [KeyboardButton("Premium"),       KeyboardButton("Sayt")],
        [KeyboardButton("Yordam")],
    ]
    if is_admin:
        rows.append([KeyboardButton("Admin Panel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_categories():
    cats = [
        ("Umumiy",          "umumiy"),
        ("Yol belgilari",   "belgilar"),
        ("Qoidalar",        "qoidalar"),
        ("Xavfsizlik",      "xavfsizlik"),
        ("Texnik holat",    "texnik"),
        ("Birinchi yordam", "birinchi-yordam"),
        ("Jarimalar",       "jarimalar"),
    ]
    btns = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(n, callback_data="cat:" + c) for n, c in cats[i:i+2]]
        btns.append(row)
    btns.append([InlineKeyboardButton("Orqaga", callback_data="nav:back")])
    return InlineKeyboardMarkup(btns)


def kb_count(cat="all"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10 ta", callback_data="go:" + cat + ":10"),
            InlineKeyboardButton("20 ta", callback_data="go:" + cat + ":20"),
        ],
        [
            InlineKeyboardButton("30 ta", callback_data="go:" + cat + ":30"),
            InlineKeyboardButton("40 ta", callback_data="go:" + cat + ":40"),
        ],
        [InlineKeyboardButton("Orqaga", callback_data="nav:cats")],
    ])


def kb_answer(options, qid):
    labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
    btns = []
    for k, v in options.items():
        if not v:
            continue
        short = (v[:40] + "...") if len(v) > 40 else v
        btns.append([InlineKeyboardButton(labels[k] + ". " + short, callback_data="ans:" + qid + ":" + k)])
    return InlineKeyboardMarkup(btns)


def kb_next_or_finish(is_last):
    if is_last:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Natijani korish", callback_data="quiz:finish")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("Keyingi savol", callback_data="quiz:next")]])


def kb_premium(prices):
    p1 = int(prices.get("price_1_hafta", 15000))
    p2 = int(prices.get("price_1_oy", 49000))
    p3 = int(prices.get("price_1_yil", 149000))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 Hafta - " + str(p1) + " som", callback_data="buy:hafta")],
        [InlineKeyboardButton("1 Oy - " + str(p2) + " som  MASHHUR", callback_data="buy:oy")],
        [InlineKeyboardButton("1 Yil - " + str(p3) + " som  TEJAM", callback_data="buy:yil")],
        [InlineKeyboardButton("Orqaga", callback_data="nav:back")],
    ])


def kb_admin():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Sorovlar",        callback_data="adm:pending"),
            InlineKeyboardButton("Statistika",      callback_data="adm:stats"),
        ],
        [
            InlineKeyboardButton("Foydalanuvchilar", callback_data="adm:users"),
            InlineKeyboardButton("Reyting",          callback_data="adm:top"),
        ],
        [InlineKeyboardButton("Broadcast",     callback_data="adm:broadcast")],
        [InlineKeyboardButton("Premium berish", callback_data="adm:give")],
    ])


def kb_approve_reject(req_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Tasdiqlash", callback_data="approve:" + req_id),
        InlineKeyboardButton("Rad etish",  callback_data="reject:" + req_id),
    ]])


# ============================================================
# UTILS
# ============================================================

def pbar(val, total, width=10):
    if not total:
        return "." * width
    filled = round(val / total * width)
    return "#" * filled + "." * (width - filled)


def fmt_time(sec):
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return str(h) + "s " + str(m) + "d"
    if m:
        return str(m) + "d " + str(s) + "s"
    return str(s) + "s"


def score_badge(score):
    if score >= 95:
        return "Ajoyib A+"
    if score >= 85:
        return "O'tdi!"
    if score >= 70:
        return "Yaxshi"
    if score >= 50:
        return "O'rta"
    return "O'tmadi"


def motivational(score):
    if score >= 95:
        return "Ajoyib! Imtihondan 100% o'tasiz!"
    if score >= 85:
        return "Zor! GAI imtihonini bemalol topshirasiz!"
    if score >= 70:
        return "Yaxshi harakat! Yana bir oz o'qing."
    if score >= 50:
        return "O'rtacha. Ko'proq mashq qiling!"
    return "Kuchsiz natija. YHQ ni qayta o'qing."


def rank_medal(i):
    medals = ["1-o'rin", "2-o'rin", "3-o'rin", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
    return medals[i] if i < len(medals) else "-"


# ============================================================
# /START
# ============================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await ensure_user(update)
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)

    if prem:
        pinfo = await get_premium_info(u.id)
        limit_text = "Cheksiz"
        badge = "PREMIUM - " + str(pinfo.get("days_left", 0)) + " kun qoldi"
        video_line = "- Video kurslar (20 dars) - OCHIQ"
        yhq_line   = "- YHQ barcha 29 bob - OCHIQ"
    else:
        limit_text = str(FREE_LIMIT - used) + "/" + str(FREE_LIMIT) + " ta"
        badge      = "Bepul"
        video_line = "- Video kurslar - faqat Premium"
        yhq_line   = "- YHQ to'liq - faqat Premium"

    text = (
        "AvtoTest.Uz\n"
        "========================\n\n"
        "Salom, " + u.first_name + "!\n"
        "Status: " + badge + "\n"
        "Bugungi limit: " + limit_text + "\n\n"
        "Nimalarga ega bo'lasiz:\n"
        "- 1000+ test savollari (7 mavzu)\n"
        "- Bot ichida test ishlash\n"
        "- Har xatoga izoh\n"
        "- Shaxsiy statistika\n"
        "- Reyting tizimi\n"
        + video_line + "\n"
        + yhq_line + "\n\n"
        "Boshlang!"
    )
    await update.message.reply_text(text, reply_markup=kb_main(u.id == ADMIN_ID))


# ============================================================
# TEST BOSHLASH
# ============================================================

async def test_start_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)

    if not prem and used >= FREE_LIMIT:
        prices = await get_settings_dict("price_1_hafta", "price_1_oy", "price_1_yil")
        text = (
            "Kunlik limit tugadi!\n\n"
            "Bugun: " + str(used) + "/" + str(FREE_LIMIT) + " ta\n"
            "Ertaga yangilanadi: " + (date.today() + timedelta(days=1)).strftime("%d.%m.%Y") + "\n\n"
            "Premium bilan CHEKSIZ:\n"
            "- Kunlik limit yo'q\n"
            "- 20 ta video dars\n"
            "- YHQ barcha boblari\n"
            "- Har xatoga izoh\n\n"
            "Tarif tanlang:"
        )
        await update.message.reply_text(text, reply_markup=kb_premium(prices))
        return

    remaining = "Cheksiz" if prem else str(FREE_LIMIT - used) + " ta qoldi"
    text = (
        "Test boshlash\n\n"
        "Qolgan limit: " + remaining + "\n\n"
        "Nechta savol?"
    )
    await update.message.reply_text(text, reply_markup=kb_count())


# ============================================================
# KATEGORIYALAR
# ============================================================

async def categories_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kategoriya tanlang:\n\nQaysi mavzuda mashq qilmoqchisiz?",
        reply_markup=kb_categories()
    )


# ============================================================
# NATIJALAR
# ============================================================

async def stats_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    s = await get_user_stats(u.id)

    if not s.get("total"):
        await update.message.reply_text(
            "Statistika\n\n"
            "Hali birorta test topshirmadingiz!\n\n"
            "Birinchi testni boshlang."
        )
        return

    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)
    badge = "Premium" if prem else "Bepul"
    limit_txt = "Cheksiz" if prem else str(FREE_LIMIT - used) + "/" + str(FREE_LIMIT)
    streak = s.get("streak", 0)
    streak_txt = "\n" + str(streak) + " kunlik seriya!" if streak > 1 else ""
    h, r = divmod(s["time"], 3600)
    m = r // 60
    bar = pbar(s["avg"], 100)

    text = (
        u.first_name + " - Natijalarim\n"
        "========================\n"
        + badge + " | Limit: " + limit_txt + streak_txt + "\n\n"
        "Umumiy:\n"
        "- Jami testlar:    " + str(s["total"]) + " ta\n"
        "- O'tdi (85%+):   " + str(s["passed"]) + " ta\n"
        "- O'tmadi:        " + str(s["failed"]) + " ta\n"
        "- O'tish darajasi: " + str(s["pass_rate"]) + "%\n\n"
        "Balllar:\n"
        "- O'rtacha:  " + str(s["avg"]) + "%  [" + bar + "]\n"
        "- Eng yuqori: " + str(s["best"]) + "%\n"
        "- Eng past:   " + str(s["worst"]) + "%\n"
        "- Jami ball:  " + str(s["points"]) + "\n\n"
        "Sarflangan vaqt: " + str(h) + "s " + str(m) + "d\n\n"
        "Oxirgi 3 test:\n"
    )
    for res in s.get("recent", []):
        d = res["date"][:10]
        sc = res["score_percentage"]
        tq = res["total_questions"]
        cc = res["correct_count"]
        mark = "OK" if sc >= PASS_SCORE else "XX"
        text += mark + " " + str(sc) + "% - " + str(cc) + "/" + str(tq) + " - " + d + "\n"

    await update.message.reply_text(text)


# ============================================================
# REYTING
# ============================================================

async def leaderboard_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = await get_leaderboard()
    u = update.effective_user

    if not top:
        await update.message.reply_text("Reyting hali shakillanmagan!\n\nBirinchi bo'ling!")
        return

    text = "TOP-" + str(len(top)) + " REYTING\n========================\n\n"
    my_rank = None
    for i, row in enumerate(top):
        name = (row.get("name") or "Noma'lum")[:18]
        pts = row.get("total_points", 0)
        line = rank_medal(i) + " " + name + " - " + str(pts) + " ball"
        if row.get("id") == make_uid(u.id):
            line += " <- Siz"
            my_rank = i + 1
        text += line + "\n"

    if my_rank:
        text += "\n========================\nSizning o'rningiz: #" + str(my_rank)
    else:
        text += "\n========================\nSiz hali top-10 da emassiz"

    await update.message.reply_text(text)


# ============================================================
# PREMIUM
# ============================================================

async def premium_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    pinfo = await get_premium_info(u.id)

    if pinfo.get("active"):
        text = (
            "PREMIUM - Faol!\n\n"
            "Tarif: " + pinfo["plan"] + "\n"
            "Tugash sanasi: " + pinfo["expires"] + "\n"
            "Qoldi: " + str(pinfo["days_left"]) + " kun\n\n"
            "Sizda mavjud:\n"
            "- Cheksiz kunlik testlar\n"
            "- 20 ta video dars\n"
            "- YHQ kitob - barcha 29 bob\n"
            "- Har xatoga batafsil izoh\n"
            "- Reyting imtiyozlari\n\n"
            "Saytda ham barcha imkoniyatlar ochiq!"
        )
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Saytni ochish", web_app=WebAppInfo(url=WEBAPP_URL))
        ]]))
        return

    prices = await get_settings_dict("price_1_hafta", "price_1_oy", "price_1_yil")
    p1 = int(prices.get("price_1_hafta", 15000))
    p2 = int(prices.get("price_1_oy", 49000))
    p3 = int(prices.get("price_1_yil", 149000))

    text = (
        "Premium Obuna\n"
        "========================\n\n"
        "Premium bilan nima olasiz:\n"
        "- Cheksiz kunlik testlar\n"
        "- 20 ta video dars\n"
        "- YHQ kitob - barcha 29 bob\n"
        "- Har xatoga batafsil izoh\n"
        "- Reyting imtiyozlari\n"
        "- Kengaytirilgan statistika\n\n"
        "========================\n"
        "Narxlar:\n\n"
        "1 Hafta - " + str(p1) + " som\n"
        "1 Oy    - " + str(p2) + " som  <- Ko'pchilik tanlaydi\n"
        "1 Yil   - " + str(p3) + " som  <- Eng tejamkor\n\n"
        "Tarif tanlang:"
    )
    await update.message.reply_text(text, reply_markup=kb_premium(prices))


# ============================================================
# SAYT
# ============================================================

async def site_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AvtoTest.Uz - To'liq Platforma\n\n"
        "Saytda qo'shimcha imkoniyatlar:\n"
        "- Video kurslar (20 ta dars)\n"
        "- YHQ - barcha 29 bob\n"
        "- Test tarixi\n"
        "- Premium boshqaruv\n\n"
        "Ochish:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Saytni ochish", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])
    )


# ============================================================
# YORDAM (ConversationHandler)
# ============================================================

async def support_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Yordam / Support\n\n"
        "Savolingiz yoki muammoingizni yozing.\n"
        "Admin 1-24 soat ichida javob beradi!\n\n"
        "To'g'ridan ham yozishingiz mumkin: @kamron201\n\n"
        "Bekor qilish: /cancel",
        reply_markup=ReplyKeyboardRemove()
    )
    return SUPPORT_WAIT


async def support_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg_text = update.message.text
    prem = await is_premium(u.id)
    badge = "PREMIUM" if prem else "Bepul"
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            "Yangi support xabari!\n\n"
            "Foydalanuvchi: " + u.first_name + "\n"
            "Status: " + badge + "\n"
            "ID: " + str(u.id) + "\n"
            "Vaqt: " + datetime.now().strftime("%d.%m.%Y %H:%M") + "\n\n"
            "Xabar:\n" + msg_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Javob berish", url="tg://user?id=" + str(u.id))
            ]])
        )
    except:
        pass
    await update.message.reply_text(
        "Xabaringiz yuborildi!\n\nAdmin tez orada javob beradi.",
        reply_markup=kb_main(u.id == ADMIN_ID)
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bekor qilindi.",
        reply_markup=kb_main(update.effective_user.id == ADMIN_ID)
    )
    return ConversationHandler.END


# ============================================================
# ADMIN PANEL
# ============================================================

async def admin_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Ruxsat yo'q!")
        return
    await send_admin_panel(update.message.reply_text)


async def send_admin_panel(send_fn):
    total_u = total_q = total_t = active_p = pending = 0
    if sb:
        try:
            total_u  = sb.table("users").select("id", count="exact").neq("role", "ADMIN").execute().count or 0
            total_q  = sb.table("questions").select("id", count="exact").execute().count or 0
            total_t  = sb.table("test_results").select("id", count="exact").execute().count or 0
            active_p = sb.table("premium_users").select("id", count="exact").gt("expires_at", datetime.now().isoformat()).execute().count or 0
            pending  = sb.table("premium_requests").select("id", count="exact").eq("status", "pending").execute().count or 0
        except:
            pass

    sorov_text = "YANGI SOROVLAR: " + str(pending) + " ta!" if pending else "Yangi sorovlar yo'q"
    text = (
        "Admin Panel\n"
        "========================\n\n"
        "Foydalanuvchilar: " + str(total_u) + "\n"
        "Savollar: "         + str(total_q) + "\n"
        "Jami testlar: "     + str(total_t) + "\n"
        "Aktiv Premium: "    + str(active_p) + "\n"
        "Kutilayotgan: "     + str(pending)  + "\n\n"
        + datetime.now().strftime("%d.%m.%Y %H:%M") + "\n\n"
        + sorov_text
    )
    await send_fn(text, reply_markup=kb_admin())


# ============================================================
# QUIZ ENGINE
# ============================================================

async def launch_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cat, count):
    u = update.effective_user
    prem = await is_premium(u.id)
    used = await get_daily_used(u.id)

    if not prem and used >= FREE_LIMIT:
        prices = await get_settings_dict("price_1_hafta", "price_1_oy", "price_1_yil")
        await update.effective_message.edit_text(
            "Kunlik limit tugadi!\n\n"
            "Bugun " + str(FREE_LIMIT) + " ta test ishladingiz.\n"
            "Premium bilan cheksiz!",
            reply_markup=kb_premium(prices)
        )
        return

    qs = await fetch_questions(count, cat)
    if not qs:
        await update.effective_message.edit_text(
            "Bu kategoriyada savollar topilmadi. Boshqa kategoriya tanlang."
        )
        return

    ctx.user_data["quiz"] = {
        "qs": qs,
        "idx": 0,
        "answers": {},
        "correct": 0,
        "cat": cat,
        "started": datetime.now().isoformat(),
    }
    try:
        await update.effective_message.delete()
    except:
        pass
    await send_quiz_question(update.effective_chat.id, ctx)


async def send_quiz_question(chat_id, ctx: ContextTypes.DEFAULT_TYPE):
    quiz = ctx.user_data.get("quiz")
    if not quiz:
        return

    q = quiz["qs"][quiz["idx"]]
    idx = quiz["idx"]
    total = len(quiz["qs"])
    bar = pbar(idx, total)
    labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}

    opts = {
        "A": q.get("option_a", ""),
        "B": q.get("option_b", ""),
        "C": q.get("option_c", ""),
        "D": q.get("option_d", ""),
    }
    if q.get("option_e"):
        opts["E"] = q["option_e"]
    opts = {k: v for k, v in opts.items() if v}

    opts_lines = "\n".join([labels[k] + ". " + v for k, v in opts.items()])
    text = (
        "Savol " + str(idx + 1) + "/" + str(total) + "\n"
        "[" + bar + "]\n"
        "To'g'ri: " + str(quiz["correct"]) + " | Xato: " + str(idx - quiz["correct"]) + "\n\n"
        + q["question_text"] + "\n\n"
        + opts_lines
    )

    if q.get("image"):
        try:
            await ctx.bot.send_photo(chat_id, q["image"], caption=text, reply_markup=kb_answer(opts, q["id"]))
            return
        except:
            pass
    await ctx.bot.send_message(chat_id, text, reply_markup=kb_answer(opts, q["id"]))


async def finish_quiz(chat_id, u, ctx: ContextTypes.DEFAULT_TYPE):
    quiz = ctx.user_data.pop("quiz", None)
    if not quiz:
        return

    total = len(quiz["qs"])
    correct = quiz["correct"]
    score = round(correct / total * 100) if total else 0
    passed = score >= PASS_SCORE
    elapsed = int((datetime.now() - datetime.fromisoformat(quiz["started"])).total_seconds())

    await save_result(u.id, quiz)
    await increment_daily(u.id)

    wrong_qs = [q for q in quiz["qs"] if quiz["answers"].get(q["id"], "") != q["correct_answer"]]
    wrong_text = ""
    if wrong_qs and not passed:
        labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
        wrong_text = "\n\nXato savollar:\n"
        for wq in wrong_qs[:5]:
            rk = wq["correct_answer"]
            rv = wq.get("option_" + rk.lower(), "")
            q_short = wq["question_text"][:55] + ("..." if len(wq["question_text"]) > 55 else "")
            wrong_text += "- " + q_short + "\n  To'g'ri: " + labels[rk] + ". " + rv[:45] + "\n"
        if len(wrong_qs) > 5:
            wrong_text += "...va yana " + str(len(wrong_qs) - 5) + " ta xato\n"

    bar = pbar(score, 100, 10)
    badge = score_badge(score)
    motiv = motivational(score)
    status = "O'TDINGIZ!" if passed else "O'TMADINGIZ"

    prem = await is_premium(u.id)
    used_now = await get_daily_used(u.id)
    limit_txt = "Cheksiz" if prem else str(FREE_LIMIT - used_now) + "/" + str(FREE_LIMIT)

    text = (
        "Test yakunlandi!\n"
        "========================\n\n"
        + status + " - " + badge + "\n\n"
        "Natija: " + str(correct) + "/" + str(total) + " to'g'ri\n"
        "Ball:   " + str(score) + "%\n"
        "[" + bar + "]\n"
        "Vaqt:   " + fmt_time(elapsed) + "\n\n"
        + motiv + "\n"
        "Limit: " + limit_txt
        + wrong_text
    )

    btns = [
        [
            InlineKeyboardButton("Qayta", callback_data="go:" + quiz["cat"] + ":" + str(total)),
            InlineKeyboardButton("Statistika", callback_data="nav:stats"),
        ],
    ]
    if not prem:
        btns.append([InlineKeyboardButton("Premium - Cheksiz test!", callback_data="nav:premium")])
    btns.append([InlineKeyboardButton("Bosh menu", callback_data="nav:back")])

    await ctx.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(btns))


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    u = q.from_user
    chat_id = update.effective_chat.id

    if d.startswith("cat:"):
        cat = d[4:]
        cat_names = {
            "umumiy":          "Umumiy",
            "belgilar":        "Yol belgilari",
            "qoidalar":        "Qoidalar",
            "xavfsizlik":      "Xavfsizlik",
            "texnik":          "Texnik holat",
            "birinchi-yordam": "Birinchi yordam",
            "jarimalar":       "Jarimalar",
        }
        prem = await is_premium(u.id)
        used = await get_daily_used(u.id)
        remaining = "Cheksiz" if prem else str(FREE_LIMIT - used) + " ta"
        await q.edit_message_text(
            cat_names.get(cat, cat) + " tanlandi!\n\n"
            "Qolgan limit: " + remaining + "\n\n"
            "Nechta savol?",
            reply_markup=kb_count(cat)
        )

    elif d.startswith("go:"):
        parts = d.split(":")
        await launch_quiz(update, ctx, parts[1], int(parts[2]))

    elif d.startswith("ans:"):
        parts = d.split(":", 2)
        qid = parts[1]
        ans = parts[2]
        quiz = ctx.user_data.get("quiz")
        if not quiz or qid in quiz["answers"]:
            return
        cq = quiz["qs"][quiz["idx"]]
        if cq["id"] != qid:
            return

        quiz["answers"][qid] = ans
        is_right = ans == cq["correct_answer"]
        if is_right:
            quiz["correct"] += 1

        labels = {"A": "F1", "B": "F2", "C": "F3", "D": "F4", "E": "F5"}
        opts = {
            "A": cq.get("option_a", ""),
            "B": cq.get("option_b", ""),
            "C": cq.get("option_c", ""),
            "D": cq.get("option_d", ""),
        }
        if cq.get("option_e"):
            opts["E"] = cq["option_e"]
        opts = {k: v for k, v in opts.items() if v}

        right_key = cq["correct_answer"]
        right_val = opts.get(right_key, "")
        user_val  = opts.get(ans, "")

        if is_right:
            result_text = "To'g'ri!\n" + labels[ans] + ". " + user_val
        else:
            result_text = (
                "Noto'g'ri!\n"
                "Siz: " + labels[ans] + ". " + user_val + "\n\n"
                "To'g'ri javob:\n" + labels[right_key] + ". " + right_val
            )

        desc = cq.get("description", "")
        if desc:
            result_text += "\n\nIzoh:\n" + desc

        is_last = quiz["idx"] >= len(quiz["qs"]) - 1
        result_text += "\n\nNatija: " + str(quiz["correct"]) + "/" + str(quiz["idx"] + 1)

        try:
            await q.edit_message_caption(result_text, reply_markup=kb_next_or_finish(is_last))
        except:
            try:
                await q.edit_message_text(result_text, reply_markup=kb_next_or_finish(is_last))
            except:
                pass

    elif d == "quiz:next":
        quiz = ctx.user_data.get("quiz")
        if not quiz:
            return
        quiz["idx"] += 1
        if quiz["idx"] >= len(quiz["qs"]):
            try:
                await q.delete_message()
            except:
                pass
            await finish_quiz(chat_id, u, ctx)
        else:
            try:
                await q.delete_message()
            except:
                pass
            await send_quiz_question(chat_id, ctx)

    elif d == "quiz:finish":
        try:
            await q.delete_message()
        except:
            pass
        await finish_quiz(chat_id, u, ctx)

    elif d.startswith("buy:"):
        plan_key = d[4:]
        plans = {
            "hafta": ("1 Hafta",  7,   "price_1_hafta"),
            "oy":    ("1 Oy",    30,   "price_1_oy"),
            "yil":   ("1 Yil",  365,   "price_1_yil"),
        }
        pname, days, pkey = plans[plan_key]
        price = int(await get_setting(pkey, "49000"))
        s = await get_settings_dict("card_number", "card_owner", "card_type")
        card_num = s.get("card_number", "0000 0000 0000 0000")
        card_own = s.get("card_owner", "Admin")
        card_typ = s.get("card_type", "Humo")
        text = (
            pname + " Premium - " + str(price) + " som\n"
            "========================\n\n"
            "To'lov rekvizitlari:\n"
            "Karta: " + card_num + "\n"
            "Egasi: " + card_own + "\n"
            "Turi:  " + card_typ + "\n\n"
            "Qadamlar:\n"
            "1. " + str(price) + " som kartaga o'tkazing\n"
            "2. To'lov chekini screenshot oling\n"
            "3. @kamron201 ga chekni yuboring\n"
            "4. Admin " + str(days) + " kunlik Premium beradi\n\n"
            "Tasdiqlash vaqti: 1-3 soat"
        )
        await q.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Chekni @kamron201 ga yuborish", url="https://t.me/kamron201")],
                [InlineKeyboardButton("Boshqa tarif", callback_data="nav:premium")],
            ])
        )

    elif d.startswith("nav:"):
        dest = d[4:]
        if dest == "back":
            try:
                await q.delete_message()
            except:
                pass
        elif dest == "cats":
            await q.edit_message_text("Kategoriya tanlang:", reply_markup=kb_categories())
        elif dest == "premium":
            prices = await get_settings_dict("price_1_hafta", "price_1_oy", "price_1_yil")
            p2 = int(prices.get("price_1_oy", 49000))
            await q.edit_message_text(
                "Premium Obuna\n\n"
                "- Cheksiz testlar\n"
                "- Video kurslar\n"
                "- YHQ kitob\n\n"
                "1 Oy - " + str(p2) + " som\n\n"
                "Tarif tanlang:",
                reply_markup=kb_premium(prices)
            )
        elif dest == "stats":
            try:
                await q.delete_message()
            except:
                pass
            s = await get_user_stats(u.id)
            text = (
                "Natijalarim\n\n"
                "Jami: "      + str(s.get("total", 0)) + " test\n"
                "O'tdi: "     + str(s.get("passed", 0)) + " ta\n"
                "O'rtacha: "  + str(s.get("avg", 0)) + "%\n"
                "Eng yaxshi: "+ str(s.get("best", 0)) + "%"
            )
            await ctx.bot.send_message(chat_id, text)

    elif d.startswith("adm:") and u.id == ADMIN_ID:
        sub = d[4:]

        if sub == "stats":
            total_u = total_q = total_t = active_p = pending = new_today = 0
            if sb:
                try:
                    total_u  = sb.table("users").select("id", count="exact").neq("role", "ADMIN").execute().count or 0
                    total_q  = sb.table("questions").select("id", count="exact").execute().count or 0
                    total_t  = sb.table("test_results").select("id", count="exact").execute().count or 0
                    active_p = sb.table("premium_users").select("id", count="exact").gt("expires_at", datetime.now().isoformat()).execute().count or 0
                    pending  = sb.table("premium_requests").select("id", count="exact").eq("status", "pending").execute().count or 0
                    new_today = sb.table("users").select("id", count="exact").gte("created_at", date.today().isoformat()).neq("role", "ADMIN").execute().count or 0
                except:
                    pass
            text = (
                "Admin - Statistika\n"
                "========================\n\n"
                "Jami foydalanuvchilar: " + str(total_u) + "\n"
                "Bugun qo'shildi: "       + str(new_today) + "\n"
                "Savollar: "              + str(total_q) + "\n"
                "Jami testlar: "          + str(total_t) + "\n"
                "Aktiv Premium: "         + str(active_p) + "\n"
                "Kutilayotgan: "          + str(pending) + "\n\n"
                + datetime.now().strftime("%d.%m.%Y %H:%M")
            )
            await q.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="adm:back")]])
            )

        elif sub == "top":
            top = await get_leaderboard()
            text = "TOP-10 REYTING\n========================\n\n"
            for i, row in enumerate(top):
                text += rank_medal(i) + " " + (row.get("name") or "?")[:18] + " - " + str(row.get("total_points", 0)) + " ball\n"
            await q.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="adm:back")]])
            )

        elif sub == "users":
            users = []
            if sb:
                try:
                    users = sb.table("users").select("name,created_at").neq("role", "ADMIN").order("created_at", desc=True).limit(10).execute().data or []
                except:
                    pass
            text = "So'nggi 10 foydalanuvchi\n========================\n\n"
            for row in users:
                text += (row.get("name") or "?")[:20] + " | " + (row.get("created_at") or "")[:10] + "\n"
            await q.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="adm:back")]])
            )

        elif sub == "pending":
            reqs = []
            if sb:
                try:
                    reqs = sb.table("premium_requests").select("*").eq("status", "pending").order("created_at", desc=True).limit(10).execute().data or []
                except:
                    pass
            if not reqs:
                await q.edit_message_text(
                    "Kutilayotgan sorovlar yo'q!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="adm:back")]])
                )
                return
            await q.edit_message_text(str(len(reqs)) + " ta sorov yuborilmoqda...")
            for req in reqs:
                req_text = (
                    "Premium Sorov\n\n"
                    "Foydalanuvchi: " + (req.get("user_name") or "?") + "\n"
                    "Tarif: "         + (req.get("plan") or "") + "\n"
                    "Narx: "          + str(req.get("price", 0)) + " som\n"
                    "Sana: "          + (req.get("created_at") or "")[:16].replace("T", " ")
                )
                try:
                    ss = req.get("screenshot_url", "")
                    if ss:
                        await ctx.bot.send_photo(ADMIN_ID, ss, caption=req_text, reply_markup=kb_approve_reject(req["id"]))
                    else:
                        await ctx.bot.send_message(ADMIN_ID, req_text, reply_markup=kb_approve_reject(req["id"]))
                except:
                    pass

        elif sub == "broadcast":
            ctx.user_data["adm_await"] = "broadcast"
            await q.edit_message_text(
                "Broadcast\n\nBarcha foydalanuvchilarga yuboriladi.\n\nXabar matnini yozing:\n(Bekor: /cancel)",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Bekor", callback_data="adm:back")]])
            )

        elif sub == "give":
            ctx.user_data["adm_await"] = "give_id"
            await q.edit_message_text(
                "Premium berish\n\nFoydalanuvchi Telegram ID sini yozing:\nmasalan: 123456789\n\n(Bekor: /cancel)",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Bekor", callback_data="adm:back")]])
            )

        elif sub == "back":
            await send_admin_panel(q.edit_message_text)

    elif d.startswith("approve:") and u.id == ADMIN_ID:
        req_id = d[8:]
        if not sb:
            await q.edit_message_text("Supabase ulanmagan!")
            return
        try:
            req = sb.table("premium_requests").select("*").eq("id", req_id).single().execute().data
            if not req:
                await q.edit_message_text("Sorov topilmadi!")
                return
            days = req.get("days", 30)
            tg_id_int = int(req["user_id"].replace("user_", "").split("_")[0])
            ok = await activate_premium_for(tg_id_int, days, req.get("plan", "Premium"))
            sb.table("premium_requests").update({"status": "approved"}).eq("id", req_id).execute()
            if ok:
                pinfo = await get_premium_info(tg_id_int)
                try:
                    await ctx.bot.send_message(
                        tg_id_int,
                        "Premium faollashdi!\n\n"
                        "Tarif: "          + req.get("plan", "Premium") + "\n"
                        "Tugash sanasi: "  + pinfo.get("expires", "?") + "\n"
                        "Kunlar: "         + str(days) + "\n\n"
                        "- Cheksiz testlar\n"
                        "- 20 ta video dars\n"
                        "- YHQ barcha boblari\n\n"
                        "Xaridingiz uchun rahmat!"
                    )
                except:
                    pass
                await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Tasdiqlangan - " + (req.get("user_name") or "?"), callback_data="noop")
                ]]))
            else:
                await q.edit_message_text("Faollashtrishda xato!")
        except Exception as e:
            await q.edit_message_text("Xato: " + str(e))

    elif d.startswith("reject:") and u.id == ADMIN_ID:
        req_id = d[7:]
        if not sb:
            return
        try:
            req = sb.table("premium_requests").select("*").eq("id", req_id).single().execute().data
            if req:
                sb.table("premium_requests").update({"status": "rejected"}).eq("id", req_id).execute()
                tg_id_str = req["user_id"].replace("user_", "").split("_")[0]
                try:
                    await ctx.bot.send_message(
                        int(tg_id_str),
                        "Premium so'rovingiz rad etildi\n\n"
                        "To'lov tasdiqlanmadi.\n"
                        "Muammo bo'lsa @kamron201 ga yozing."
                    )
                except:
                    pass
                await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Rad etildi - " + (req.get("user_name") or "?"), callback_data="noop")
                ]]))
        except Exception as e:
            await q.edit_message_text("Xato: " + str(e))


# ============================================================
# ADMIN TEXT HANDLER
# ============================================================

async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return False
    action = ctx.user_data.get("adm_await")
    if not action:
        return False

    msg_text = update.message.text
    ctx.user_data.pop("adm_await", None)

    if action == "broadcast":
        users = []
        if sb:
            try:
                users = sb.table("users").select("id").neq("role", "ADMIN").execute().data or []
            except:
                pass
        await update.message.reply_text("Yuborilmoqda... (" + str(len(users)) + " ta foydalanuvchi)")
        sent = failed = 0
        for row in users:
            try:
                tg_id = int(row["id"].replace("user_", "").split("_")[0])
                await ctx.bot.send_message(
                    tg_id,
                    "AvtoTest.Uz - Yangilik!\n\n" + msg_text + "\n\n" + WEBAPP_URL
                )
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await update.message.reply_text(
            "Broadcast yakunlandi!\n\nYuborildi: " + str(sent) + "\nXato: " + str(failed)
        )

    elif action == "give_id":
        try:
            tg_id = int(msg_text.strip())
            ctx.user_data["give_tg_id"] = tg_id
            ctx.user_data["adm_await"] = "give_days"
            await update.message.reply_text("ID: " + str(tg_id) + "\n\nNecha kunlik Premium berasiz?")
        except:
            await update.message.reply_text("Noto'g'ri ID! Faqat raqam kiriting.")

    elif action == "give_days":
        tg_id = ctx.user_data.pop("give_tg_id", None)
        if not tg_id:
            await update.message.reply_text("Xato. Qaytadan bosing.")
            return True
        try:
            days = int(msg_text.strip())
            ok = await activate_premium_for(tg_id, days, "Admin sovgasi " + str(days) + " kun")
            if ok:
                try:
                    await ctx.bot.send_message(
                        tg_id,
                        "Premium sovga oldi!\n\n"
                        "Admin tomonidan " + str(days) + " kunlik Premium berildi!\n\n"
                        "- Cheksiz testlar\n"
                        "- Video kurslar\n"
                        "- YHQ barcha boblari\n\n"
                        "Unumli foydalaning!"
                    )
                except:
                    pass
                await update.message.reply_text(str(tg_id) + " ga " + str(days) + " kunlik Premium berildi!")
            else:
                await update.message.reply_text("Premium berishda xato!")
        except:
            await update.message.reply_text("Noto'g'ri kun soni!")

    return True


# ============================================================
# MESSAGE ROUTER
# ============================================================

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg_text = update.message.text or ""

    if u.id == ADMIN_ID and ctx.user_data.get("adm_await"):
        if await handle_admin_text(update, ctx):
            return

    await ensure_user(update)
    is_adm = (u.id == ADMIN_ID)

    if msg_text == "Test boshlash":
        await test_start_msg(update, ctx)
    elif msg_text == "Kategoriyalar":
        await categories_msg(update, ctx)
    elif msg_text == "Natijalarim":
        await stats_msg(update, ctx)
    elif msg_text == "Reyting":
        await leaderboard_msg(update, ctx)
    elif msg_text == "Premium":
        await premium_msg(update, ctx)
    elif msg_text == "Sayt":
        await site_msg(update, ctx)
    elif msg_text == "Admin Panel" and is_adm:
        await admin_msg(update, ctx)
    else:
        await update.message.reply_text(
            "Pastdagi menyudan foydalaning:",
            reply_markup=kb_main(is_adm)
        )


# ============================================================
# COMMANDS
# ============================================================

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await test_start_msg(update, ctx)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await stats_msg(update, ctx)

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await leaderboard_msg(update, ctx)

async def cmd_premium_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await premium_msg(update, ctx)

async def cmd_admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await admin_msg(update, ctx)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AvtoTest.Uz Bot - Yordam\n"
        "========================\n\n"
        "Buyruqlar:\n"
        "/start   - Bosh menyu\n"
        "/test    - Test boshlash\n"
        "/stats   - Natijalarim\n"
        "/top     - Reyting\n"
        "/premium - Premium\n"
        "/help    - Yordam\n\n"
        "Qanday ishlaydi:\n"
        "1. Test boshlang (10/20/30/40 savol)\n"
        "2. Har savolga F1-F4 dan javob bering\n"
        "3. Har javobdan keyin to'g'ri javob chiqadi\n"
        "4. Test tugagach batafsil natija chiqadi\n\n"
        "Bepul: kuniga " + str(FREE_LIMIT) + " ta test\n"
        "Premium: cheksiz + videolar + YHQ\n\n"
        "Muammo: @kamron201"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Yordam$"), support_entry)],
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
    app.add_handler(CommandHandler("premium", cmd_premium_cmd))
    app.add_handler(CommandHandler("admin", cmd_admin_cmd))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(support_conv)
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("AvtoTest.Uz Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
