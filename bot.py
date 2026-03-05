import os
import random
import asyncio
import logging
from datetime import datetime, timezone
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Railway Variables ustunlik qiladi — .env faqat local uchun
load_dotenv(override=False)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ===================== SOZLAMALAR =====================
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://avto-test-uz-three.vercel.app")
ADMIN_URL  = "https://t.me/kamron201"

# Majburiy obuna kanali
CHANNEL_USERNAME = "@premium_milliy"
CHANNEL_URL      = "https://t.me/premium_milliy"

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Ishga tushishdan oldin tekshirish
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN Railway Variables da topilmadi!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL yoki SUPABASE_KEY Railway Variables da topilmadi!")

logger.info(f"SUPABASE_URL: {SUPABASE_URL[:40]}")
logger.info(f"SUPABASE_KEY: {SUPABASE_KEY[:20]}...")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stikerlar (ishlamasa try/except bilan o'tib ketadi)
STICKER_WELCOME = "CAACAgIAAxkBAAIBsWd5bJ9VHpY6Y2BqGNqvE_l2fLlCAAIDAAP3AaQR2pGqAAHxHi4XNQQ"
STICKER_TEST    = "CAACAgIAAxkBAAIBs2d5bKhidvOlhYnHkixHqvJE7IKKAAIGAAPSQCQTMKCd-bRs_ZQNBQ"
STICKER_PREMIUM = "CAACAgIAAxkBAAIBtWd5bLjxKb7UJHK7hPlRGO21BFHhAAIKAAPSQCQT2nGe5GkDZGQNBQ"
STICKER_STATS   = "CAACAgIAAxkBAAIBt2d5bME1zT_f6V5v3cMR_3q1WL-ZAAINAAPOQCQT7LNbO0YGAAHMDZINBQ"

# Kanal chatda /start hisoblagichi: chat_id -> son
# 5 marta yozilsa quiz yuboriladi, so'ng hisoblagich nolga tushadi
start_counter: dict = defaultdict(int)

# @Rulda_test_chat da 5x /start bosilganda savollar SHU kanalga yuboriladi
QUIZ_TARGET_CHANNEL = "@RuldaTest"

# ===================== DATABASE =====================
def save_user(user_id: int, username: str, full_name: str) -> None:
    """Yangi foydalanuvchini Supabase ga saqlash (takroran saqlamaydi)."""
    try:
        existing = (
            supabase.table("bot_users")
            .select("user_id")
            .eq("user_id", user_id)
            .execute()
        )
        if not existing.data:
            supabase.table("bot_users").insert({
                "user_id":   user_id,
                "username":  username,
                "full_name": full_name,
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as exc:
        logger.error(f"save_user xatosi: {exc}")


def save_test(user_id: int) -> None:
    """Test sessiyasini Supabase ga yozish."""
    try:
        supabase.table("bot_test_sessions").insert({
            "user_id":    user_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        logger.error(f"save_test xatosi: {exc}")


def get_stats() -> tuple:
    """Jami va bugungi statistikani qaytaradi."""
    try:
        total_users = (
            supabase.table("bot_users")
            .select("user_id", count="exact")
            .execute().count or 0
        )
        total_tests = (
            supabase.table("bot_test_sessions")
            .select("id", count="exact")
            .execute().count or 0
        )
        today      = datetime.now(timezone.utc).date().isoformat()
        today_start = today + "T00:00:00"
        today_end   = today + "T23:59:59"

        today_users = (
            supabase.table("bot_users")
            .select("user_id", count="exact")
            .gte("joined_at", today_start)
            .lte("joined_at", today_end)
            .execute().count or 0
        )
        today_tests = (
            supabase.table("bot_test_sessions")
            .select("id", count="exact")
            .gte("started_at", today_start)
            .lte("started_at", today_end)
            .execute().count or 0
        )
        return total_users, total_tests, today_users, today_tests
    except Exception as exc:
        logger.error(f"get_stats xatosi: {exc}")
        return 0, 0, 0, 0


def get_random_questions(count: int = 20) -> list:
    """
    Supabase questions jadvalidan tasodifiy 20 ta savol oladi.
    Kamida 2 ta varianti bor savollar tanlanadi.
    """
    try:
        res = supabase.table("questions").select(
            "id, question_text, option_a, option_b, option_c, "
            "option_d, option_e, option_f, correct_answer"
        ).execute()
        all_questions = res.data or []
        # Kamida 2 ta to'liq variant bor savollarni filtrlash
        valid = [
            q for q in all_questions
            if q.get("option_a") and q.get("option_b")
        ]
        if not valid:
            return []
        sample_count = min(count, len(valid))
        return random.sample(valid, sample_count)
    except Exception as exc:
        logger.error(f"get_random_questions xatosi: {exc}")
        return []

# ===================== KANAL OBUNA TEKSHIRUVI =====================
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi @premium_milliy kanaliga obuna bo'lganini tekshiradi."""
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id,
        )
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.warning(f"Kanal tekshirishda xato: {exc}")
        # Bot kanalda admin bo'lmasa — o'tkazib yuboramiz
        return True


async def send_subscribe_prompt(update: Update) -> None:
    """Kanalga obuna bo'lish so'rovi xabarini yuboradi."""
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

# ===================== QUIZ — KANALGA SAVOLLAR YUBORISH =====================
async def send_quiz_to_chat(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Supabase dan 20 ta tasodifiy savol olib, Telegram Quiz Poll sifatida
    kanal chatiga birma-bir yuboradi.

    Qo'shish kerak bo'lsa: bu funksiyani start() ichidan chaqiring.
    """
    questions = get_random_questions(20)

    if not questions:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ Savollar topilmadi!\n\n"
                "Saytda savollar mavjudligini tekshiring: "
                f"{WEBAPP_URL}"
            ),
        )
        return

    # Boshlanish xabari
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🚗 *Yangi test boshlandi!*\n\n"
            f"📌 *Savollar soni:* {len(questions)} ta\n"
            "✅ *O'tish bali:* 85% va undan yuqori\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 Har bir savolga javob bering:"
        ),
        parse_mode="Markdown",
    )

    # Har bir savolni Telegram Quiz Poll sifatida yuborish
    for i, q in enumerate(questions, start=1):
        try:
            # Variantlarni yig'ish — bo'sh bo'lmaganlarini
            raw_options = [
                ("A", q.get("option_a") or ""),
                ("B", q.get("option_b") or ""),
                ("C", q.get("option_c") or ""),
                ("D", q.get("option_d") or ""),
                ("E", q.get("option_e") or ""),
                ("F", q.get("option_f") or ""),
            ]
            options = [
                (label, val.strip())
                for label, val in raw_options
                if val.strip()
            ]

            if len(options) < 2:
                logger.warning(f"Savol #{i} (id={q['id']}) da variant yetarli emas, o'tkazildi")
                continue

            # To'g'ri javob indeksini topish
            correct_label = (q.get("correct_answer") or "A").strip().upper()
            correct_index = 0
            for idx, (label, _) in enumerate(options):
                if label == correct_label:
                    correct_index = idx
                    break

            # Variant matnlari (Telegram 100 belgiga cheklaydi)
            option_texts = [val[:100] for _, val in options]

            # Savol matni (Telegram 255 belgiga cheklaydi)
            q_text = f"#{i} {(q.get('question_text') or '').strip()}"
            if len(q_text) > 255:
                q_text = q_text[:252] + "..."

            await context.bot.send_poll(
                chat_id=chat_id,
                question=q_text,
                options=option_texts,
                type="quiz",
                correct_option_id=correct_index,
                is_anonymous=True,
            )

            # Flood limit dan saqlanish (Telegram: max 1 poll/sek)
            await asyncio.sleep(1.5)

        except Exception as exc:
            logger.error(f"Savol #{i} yuborishda xato: {exc}")
            await asyncio.sleep(2)
            continue

    # Yakuniy xabar
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ *Test tugadi!*\n\n"
            "Yana test ishlashni xohlasangiz botga "
            "«🚗 Testni boshlash» tugmasini bosing:\n"
            "👉 @RuldaTestBot"
        ),
        parse_mode="Markdown",
    )

# ===================== MENYU =====================
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚗 Testni boshlash")],
            [KeyboardButton("📚 Qoidalar kitobi"), KeyboardButton("⭐ Premium")],
            [KeyboardButton("📊 Statistika"),      KeyboardButton("ℹ️ Yordam")],
        ],
        resize_keyboard=True,
    )


async def send_welcome(
    chat_id: int,
    first_name: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Obuna tasdiqlangandan so'ng xush kelibsiz xabari."""
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=STICKER_WELCOME)
    except Exception:
        pass  # Stiker ishlamasa davom etaveradi

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ *Tabriklaymiz! Obuna tasdiqlandi.*\n\n"
            f"👋 Xush kelibsiz, *{first_name}*!\n\n"
            f"🚗 [RuldaTest.uz]({WEBAPP_URL}) ga xush kelibsiz!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 *Bu bot nimaga kerak?*\n\n"
            "✅ Haydovchilik imtihoniga tayyorlanish\n"
            "📝 1000+ ta test savoli\n"
            "🏆 Real GAI imtihoni muhiti\n"
            "📊 Natijalaringizni kuzatish\n"
            "⭐ Premium — cheksiz imkoniyatlar\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 Quyidagi menyudan boshlang!"
        ),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

# ===================== HANDLERLAR =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start buyrug'i ikki xil holatda ishlaydi:

    1. GURUH / KANAL CHAT (@Rulda_test_chat):
       Har /start@RuldaTestBot bosilganda hisoblagich +1.
       5 ta to'lsa → 20 ta tasodifiy quiz kanalga yuboriladi,
       hisoblagich nolga tushadi.

    2. SHAXSIY CHAT:
       Kanalga obuna tekshiriladi → xush kelibsiz xabari.

    Yangi chat qo'shilsa: shu funksiyada chat.type ni tekshirish yetarli.
    """
    user    = update.effective_user
    chat    = update.effective_chat
    message = update.message

    # ── GURUH / SUPERGROUP / KANAL CHAT ──
    if chat and chat.type in ("group", "supergroup", "channel"):
        chat_id = chat.id
        start_counter[chat_id] += 1
        count = start_counter[chat_id]

        if count < 5:
            remaining = 5 - count
            await message.reply_text(
                f"📊 Test boshlash uchun yana *{remaining} ta* /start yuboring!",
                parse_mode="Markdown",
            )
        else:
            # 5 ta to'ldi — @RuldaTest kanaliga quiz yuborish
            start_counter[chat_id] = 0
            await message.reply_text(
                f"🚀 *20 ta test savoli @RuldaTest kanaliga yuklanmoqda...*\n\nBiroz kuting ⏳",
                parse_mode="Markdown",
            )
            # Background task — bot bloklanib qolmasin
            asyncio.create_task(send_quiz_to_chat(QUIZ_TARGET_CHANNEL, context))
        return

    # ── SHAXSIY CHAT ──
    save_user(user.id, user.username or "", user.full_name or "")

    if not await is_subscribed(user.id, context):
        await send_subscribe_prompt(update)
        return

    await send_welcome(user.id, user.first_name, context)


async def check_sub_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """✅ Obuna bo'ldim tugmasi bosilganda."""
    query = update.callback_query
    await query.answer()
    user  = query.from_user

    if await is_subscribed(user.id, context):
        try:
            await query.message.delete()
        except Exception:
            pass
        save_user(user.id, user.username or "", user.full_name or "")
        await send_welcome(user.id, user.first_name, context)
    else:
        await query.answer(
            "❌ Siz hali kanalga obuna bo'lmagansiz!\n\n"
            "Avval «📢 Kanalga o'tish» tugmasini bosing va obuna bo'ling.",
            show_alert=True,
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Shaxsiy chat xabarlari.
    Guruh/kanal xabarlari bu yerga tushmaydi (filters.ChatType.PRIVATE).

    Yangi menyu tugmasi qo'shish kerak bo'lsa:
    → main_menu() ga tugma qo'shing
    → bu yerda elif text == "YANGI TUGMA": bloki qo'shing
    """
    user = update.effective_user
    text = update.message.text or ""

    # Har safar obunani tekshirish
    if not await is_subscribed(user.id, context):
        await send_subscribe_prompt(update)
        return

    # ── 🚗 TEST BOSHLASH ──
    if text == "🚗 Testni boshlash":
        save_test(user.id)
        try:
            await update.message.reply_sticker(STICKER_TEST)
        except Exception:
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
                InlineKeyboardButton(
                    "🚀 Testni boshlash!",
                    web_app=__import__("telegram").WebAppInfo(url=WEBAPP_URL),
                )
            ]]),
        )

    # ── 📚 QOIDALAR KITOBI ──
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
                InlineKeyboardButton(
                    "📖 Qoidalarni o'qish",
                    url="https://lex.uz/acts/-2850459",
                )
            ]]),
        )

    # ── ⭐ PREMIUM ──
    elif text == "⭐ Premium":
        try:
            await update.message.reply_sticker(STICKER_PREMIUM)
        except Exception:
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
                InlineKeyboardButton(
                    "⭐ Premium olish",
                    web_app=__import__("telegram").WebAppInfo(url=WEBAPP_URL),
                )
            ]]),
        )

    # ── 📊 STATISTIKA ──
    elif text == "📊 Statistika":
        try:
            await update.message.reply_sticker(STICKER_STATS)
        except Exception:
            pass
        total_users, total_tests, today_users, today_tests = get_stats()
        await update.message.reply_text(
            "📊 *Bot statistikasi*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 *Jami foydalanuvchilar:* {total_users} ta\n"
            f"📝 *Jami testlar:* {total_tests} ta\n\n"
            "📅 *Bugun:*\n"
            f"   🆕 Yangi foydalanuvchilar: {today_users} ta\n"
            f"   🧪 Testlar boshlandi: {today_tests} ta\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown",
        )

    # ── ℹ️ YORDAM ──
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
            ]]),
        )

    else:
        await update.message.reply_text(
            "👇 Pastdagi menyudan foydalaning:",
            reply_markup=main_menu(),
        )

# ===================== MAIN =====================
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # /start — ham shaxsiy, ham guruh/kanal chatda ishlaydi
    app.add_handler(CommandHandler("start", start))

    # ✅ Obuna bo'ldim tugmasi
    app.add_handler(
        CallbackQueryHandler(check_sub_callback, pattern="^check_sub$")
    )

    # Shaxsiy chat xabarlari (guruh/kanal xabarlari e'tiborga olinmaydi)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_message,
        )
    )

    logger.info("✅ AvtoTest.Uz Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
