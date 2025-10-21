# -*- coding: utf-8 -*-
"""
KinoTreylerUz_Bot (webhook / Flask) — to'liq ishga tayyor kod
- TOKEN, ADMIN_ID, WEBHOOK_URL ni fayl boshida o'zgartiring.
- JSON fayllar: movies.json, channels.json, stats.json (UTF-8 bilan saqlansin)
- Run: Render yoki boshqa hostingda (Flask qabul qiladi)
"""

import os
import json
import logging
from flask import Flask, request, Response
import telebot
from telebot import types

# ---------------- CONFIG (shu yerni o'zgartiring) ----------------
TOKEN = "7928013094:AAGlDJfmjmJh_xLV3t3drzCMVnDT7tpv7ws"  # <-- bu yerga tokeningiz
ADMIN_ID = 912998145                                  # <-- o'zingizning Telegram ID (integer)
WEBHOOK_URL = "https://kinotreyleruz-bot-pq4y.onrender.com"  # <-- Render URL (o'zgartiring)
# ----------------------------------------------------------------

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# bot va flask
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# fayl nomlari
MOVIES_FILE = "movies.json"
CHANNELS_FILE = "channels.json"
STATS_FILE = "stats.json"

# ---------------- JSON yordamchi (UTF-8 / BOM muammosiz) ----------------
def ensure_file(path, default):
    """Agar fayl bo'lmasa, yaratadi va default qiymat yozadi."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

def load_json(path, default=None):
    """
    Fayldan o'qiydi. UTF-8 BOM (utf-8-sig) bilan ham ishlaydi.
    Agar o'qishda xatolik bo'lsa, default qiymat qaytarilib fayl tiklanadi.
    """
    if default is None:
        default = [] if path != STATS_FILE else {"users": []}
    ensure_file(path, default)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        # format tekshirish
        if path == STATS_FILE:
            if not isinstance(data, dict) or "users" not in data or not isinstance(data["users"], list):
                raise ValueError("stats.json format not valid")
        else:
            if not isinstance(data, list):
                raise ValueError(f"{path} must be a list")
        return data
    except Exception as e:
        logger.warning("load_json fallback for %s: %s", path, e)
        # tiklash
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default

def save_json(path, data):
    """UTF-8 formatda yozadi (BOMsiz)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- fayllarni tayyorlash ----------------
ensure_paths = [MOVIES_FILE, CHANNELS_FILE, STATS_FILE]
for p in ensure_paths:
    if p == STATS_FILE:
        ensure_file(p, {"users": []})
    else:
        ensure_file(p, [])

# ---------------- foydalanuvchi va kanallar ----------------
def add_user_if_new(user_id):
    stats = load_json(STATS_FILE, {"users": []})
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_json(STATS_FILE, stats)

def user_is_subscribed_all(user_id):
    """Majburiy kanallar ro'yxatiga qarab tekshiradi."""
    channels = load_json(CHANNELS_FILE, [])
    if not channels:
        return True, []
    not_member = []
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                not_member.append(ch)
        except Exception as e:
            # agar bot kanalda bo'lmasa yoki boshqa xatolik bo'lsa - a'zo emas deb hisoblaymiz
            logger.info("check channel error for %s on %s: %s", user_id, ch, e)
            not_member.append(ch)
    return len(not_member) == 0, not_member

# ---------------- Command handlerlar ----------------
@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message):
    add_user_if_new(message.from_user.id)
    txt = (
        f"👋 Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        "🎬 <b>KinoTreylerUz_Bot</b>\n\n"
        "📌 Kino olish uchun kinoning raqamini yuboring (masalan: 1)\n"
        "🔧 Admin uchun: /admin\n"
        "📢 Majburiy kanallar: /channels"
    )
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=["channels"])
def handle_channels(message):
    channels = load_json(CHANNELS_FILE, [])
    if not channels:
        bot.send_message(message.chat.id, "📭 Majburiy kanallar ro‘yxati bo‘sh.")
        return
    text = "<b>📢 Majburiy kanallar:</b>\n" + "\n".join(str(x) for x in channels)
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["admin"])
def handle_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Siz admin emassiz.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Kino qo‘shish", "🗑 Kino o‘chirish")
    markup.add("➕ Kanal qo‘shish", "📋 Kanal ro‘yxati")
    markup.add("📊 Statistika", "🔚 Chiqish")
    bot.send_message(message.chat.id, "🔧 Admin panel:", reply_markup=markup)

# admin state (in-memory)
admin_state = {}  # {admin_id: {"action":..., "temp_name":...}}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text is not None)
def admin_panel_text(message):
    text = message.text.strip()
    uid = message.from_user.id

    if text == "🔚 Chiqish":
        admin_state.pop(uid, None)
        bot.send_message(message.chat.id, "🔚 Admin rejimidan chiqildi.", reply_markup=types.ReplyKeyboardRemove())
        return

    if text == "➕ Kino qo‘shish":
        admin_state[uid] = {"action": "waiting_name"}
        bot.send_message(message.chat.id, "🎬 Iltimos, kinoning nomini yuboring:")
        return

    if text == "🗑 Kino o‘chirish":
        movies = load_json(MOVIES_FILE, [])
        if not movies:
            bot.send_message(message.chat.id, "📭 Hozircha kinolar yo'q.")
            return
        txt = "🎞 Mavjud kinolar:\n" + "\n".join(f"{m['id']}. {m['name']}" for m in movies)
        admin_state[uid] = {"action": "waiting_del"}
        bot.send_message(message.chat.id, txt + "\n\n❗ O'chirmoqchi bo'lgan kino ID sini yuboring:")
        return

    if text == "➕ Kanal qo‘shish":
        admin_state[uid] = {"action": "waiting_channel"}
        bot.send_message(message.chat.id, "📢 Kanal username yoki chat_id yuboring (masalan: @kanal yoki -100123...):")
        return

    if text == "📋 Kanal ro‘yxati":
        channels = load_json(CHANNELS_FILE, [])
        if not channels:
            bot.send_message(message.chat.id, "📭 Hozircha majburiy kanallar yo'q.")
            return
        bot.send_message(message.chat.id, "<b>📢 Majburiy kanallar:</b>\n" + "\n".join(channels))
        return

    if text == "📊 Statistika":
        stats = load_json(STATS_FILE, {"users": []})
        users = stats.get("users", []) if isinstance(stats, dict) else []
        bot.send_message(message.chat.id, f"📈 Foydalanuvchilar soni: {len(users)}")
        return

    # holatga qarab davom etish
    state = admin_state.get(uid)
    if not state:
        return

    if state.get("action") == "waiting_name":
        name = text
        admin_state[uid] = {"action": "waiting_video", "temp_name": name}
        bot.send_message(message.chat.id, f"🎬 Nom: <b>{name}</b>\n📹 Endi video yuboring (video/document/animation).")
        return

    if state.get("action") == "waiting_del":
        try:
            mid = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❗ Iltimos, to‘g‘ri raqam yuboring.")
            return
        movies = load_json(MOVIES_FILE, [])
        new_movies = [m for m in movies if m.get("id") != mid]
        if len(new_movies) == len(movies):
            admin_state.pop(uid, None)
            bot.send_message(message.chat.id, "❌ Bunday ID topilmadi.")
            return
        # qayta raqamlaymiz
        for i, m in enumerate(new_movies, start=1):
            m["id"] = i
        save_json(MOVIES_FILE, new_movies)
        admin_state.pop(uid, None)
        bot.send_message(message.chat.id, f"✅ {mid}-raqamli kino o‘chirildi.")
        return

    if state.get("action") == "waiting_channel":
        ch = text
        channels = load_json(CHANNELS_FILE, [])
        if ch in channels:
            admin_state.pop(uid, None)
            bot.send_message(message.chat.id, "⚠️ Bu kanal allaqachon ro‘yxatda.")
            return
        channels.append(ch)
        save_json(CHANNELS_FILE, channels)
        admin_state.pop(uid, None)
        bot.send_message(message.chat.id, f"✅ Kanal qo‘shildi: {ch}")
        return

# media handler (admin video yuborishi)
@bot.message_handler(content_types=["video", "document", "animation"])
def media_handler(message):
    uid = message.from_user.id
    state = admin_state.get(uid)
    if not state or state.get("action") != "waiting_video":
        # agar admin video yubormayotgan bo'lsa, oddiy foydalanuvchi uchun hech narsa
        return
    name = state.get("temp_name", "Nom berilmagan")
    file_id = None
    if message.content_type == "video" and message.video:
        file_id = message.video.file_id
    elif message.content_type == "animation" and message.animation:
        file_id = message.animation.file_id
    elif message.content_type == "document" and message.document:
        file_id = message.document.file_id
    if not file_id:
        bot.send_message(message.chat.id, "❗ Bu fayl video emas. Iltimos haqiqiy video yuboring.")
        return
    movies = load_json(MOVIES_FILE, [])
    next_id = 1
    if movies:
        ids = [m.get("id", 0) for m in movies if isinstance(m, dict)]
        next_id = max(ids) + 1 if ids else 1
    movies.append({"id": next_id, "name": name, "file_id": file_id})
    save_json(MOVIES_FILE, movies)
    admin_state.pop(uid, None)
    bot.send_message(message.chat.id, f"✅ Kino qo‘shildi: {next_id}. {name}")

# user sends a digit to receive a movie
@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.strip().isdigit())
def send_movie_by_number(message):
    user_id = message.chat.id
    add_user_if_new(message.from_user.id)
    ok, not_member = user_is_subscribed_all(user_id)
    if not ok:
        channels = load_json(CHANNELS_FILE, [])
        if not channels:
            bot.send_message(user_id, "📭 Majburiy kanal topilmadi.")
            return
        # inline tugmalar ko'rsatish
        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            url = None
            if isinstance(ch, str) and ch.startswith("@"):
                url = f"https://t.me/{ch.lstrip('@')}"
            else:
                # agar chat_id bo'lsa, url topilmasligi mumkin
                try:
                    info = bot.get_chat(ch)
                    if getattr(info, "username", None):
                        url = f"https://t.me/{info.username}"
                except:
                    url = None
            if url:
                markup.add(types.InlineKeyboardButton(f"📢 {ch}", url=url))
            else:
                markup.add(types.InlineKeyboardButton(f"📢 {ch}", callback_data="noop"))
        markup.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
        bot.send_message(user_id, "⚠️ Avval majburiy kanallarga a’zo bo‘ling, keyin Tekshirish tugmasini bosing:", reply_markup=markup)
        return

    num = int(message.text.strip())
    movies = load_json(MOVIES_FILE, [])
    movie = next((m for m in movies if m.get("id") == num), None)
    if not movie:
        bot.send_message(user_id, "❌ Bunday IDdagi kino topilmadi.")
        return
    try:
        bot.send_video(user_id, movie.get("file_id"), caption=f"🎬 {movie.get('name')}")
    except Exception as e:
        logger.exception("send_video error: %s", e)
        bot.send_message(user_id, "⚠️ Kino yuborishda xatolik yuz berdi.")

# callback queries (check_subs, noop)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: telebot.types.CallbackQuery):
    data = call.data
    uid = call.from_user.id
    if data == "check_subs":
        ok, not_member = user_is_subscribed_all(uid)
        if ok:
            bot.answer_callback_query(call.id, "✅ A'zo bo'lgansiz — endi kinoni so'rang.", show_alert=True)
            bot.send_message(uid, "🎉 Rahmat! Endi kinoning raqamini yuboring (masalan: 1).")
        else:
            bot.answer_callback_query(call.id, "❌ Hali ham barcha kanallarga a'zo emassiz.", show_alert=True)
    elif data == "noop":
        bot.answer_callback_query(call.id, "Bu tugma orqali to'g'ridan-to'g'ri o'tish mumkin emas.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "Tugma bosildi.", show_alert=False)

# fallback handler for unknown messages
@bot.message_handler(func=lambda m: True, content_types=['text'])
def fallback_text(message):
    # agar admin bo'lsa va admin_state holati bo'lsa, admin handler yuqoridagi funksiyalar orqali ishlaydi
    # oddiy foydalanuvchiga oddiy yo'riqnoma
    if message.text and message.text.strip().lower() in ("help", "/help"):
        bot.send_message(message.chat.id, "📌 Raqam yuboring (masalan: 1) — kinoni olasiz. /channels — majburiy kanallar")
        return
    # boshqa holatlarda kichik eslatma
    bot.send_message(message.chat.id, "🛈 Raqam yuboring yoki /channels ni bosing. Yordam uchun /admin (faqat admin).")

# ---------------- Flask webhook endpoints ----------------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_handler():
    """Telegram update sini qabul qiladi va bot ga uzatadi."""
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        logger.exception("Webhook processing error: %s", e)
    return Response("OK", status=200)

@app.route("/", methods=["GET"])
def index():
    return "<b>KinoTreylerUz_Bot - Webhook running</b>"

# ---------------- start / set webhook (faqat __main__) ----------------
def set_webhook():
    url = WEBHOOK_URL.rstrip("/") + "/" + TOKEN
    try:
        bot.remove_webhook()
        result = bot.set_webhook(url=url)
        logger.info("set_webhook result: %s", result)
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)

if __name__ == "__main__":
    # agar PORT environment da berilgan bo'lsa, Flask shu portda ishlaydi (Render shunga mos)
    port = int(os.environ.get("PORT", 10000))
    # Webhookni set qilamiz
    set_webhook()
    # Flask run — Render bunda app ni ishga tushiradi
    app.run(host="0.0.0.0", port=port)
