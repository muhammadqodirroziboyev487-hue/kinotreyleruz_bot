# -*- coding: utf-8 -*-
"""
KinoTreylerUz_Bot — Full Pro (Telegram video uploads)
Features:
- SQLite DB (movies, users, channels, news, referrals, admins)
- Add/delete movies via bot (admin). Video/file uploads accepted.
- Genres, premium flag, likes/dislikes (rating), views count.
- Random movie, search, get by ID.
- Daily news (scheduled), backups (scheduled).
- Multiple admins, give/revoke premium, referrals, user settings (lang, theme).
- Top movies graph (matplotlib), stats for admins.
- Webhook via Flask (suitable for Render).
"""

import os
import sqlite3
import logging
import time
import random
import shutil
from datetime import datetime
from flask import Flask, request, Response
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------- CONFIG (o'zgartiring agar kerak bo'lsa) ----------------
TOKEN = "7681707411:AAG0OyCUYK5D9ihYiHg7v4NJ8FebK-2p1-A"   # <-- siz bergan token
MAIN_ADMIN_ID = 912998145                                 # <-- siz bergan admin id
WEBHOOK_URL = "https://kinotreyleruz-bot-pq4y.onrender.com" # <-- Render URL (o'zgartirish mumkin)
DB_FILE = "bot.db"
BACKUP_DIR = "backups"
# -----------------------------------------------------------------------

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot + Flask
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# ---------------- Database helpers ----------------
def conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    c = conn()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_id TEXT NOT NULL,
        genre TEXT,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        dislikes INTEGER DEFAULT 0,
        premium INTEGER DEFAULT 0,
        added_by INTEGER,
        added_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        first_name TEXT,
        is_premium INTEGER DEFAULT 0,
        lang TEXT DEFAULT 'uz',
        theme TEXT DEFAULT 'day',
        referrals INTEGER DEFAULT 0,
        joined_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifier TEXT UNIQUE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,
        content TEXT,
        caption TEXT,
        scheduled INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY
    )
    """)
    # ensure main admin exists
    try:
        cur.execute("INSERT OR IGNORE INTO admins (id) VALUES (?)", (MAIN_ADMIN_ID,))
    except:
        pass
    c.commit()
    c.close()

init_db()

# ---------------- Utilities ----------------
def add_user_if_new(user):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM users WHERE id=?", (user.id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (id, first_name, joined_at) VALUES (?, ?, ?)",
                    (user.id, getattr(user, "first_name", "") or "", datetime.utcnow().isoformat()))
        c.commit()
    c.close()

def is_admin(user_id):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM admins WHERE id=?", (user_id,))
    res = cur.fetchone()
    c.close()
    return res is not None

def add_admin(user_id):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (id) VALUES (?)", (user_id,))
    c.commit()
    c.close()

def remove_admin(user_id):
    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM admins WHERE id=?", (user_id,))
    c.commit()
    c.close()

def set_user_premium(user_id, val):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE users SET is_premium=? WHERE id=?", (1 if val else 0, user_id))
    c.commit()
    c.close()

def add_channel(identifier):
    c = conn()
    cur = c.cursor()
    try:
        cur.execute("INSERT INTO channels (identifier) VALUES (?)", (identifier,))
        c.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    c.close()
    return ok

def remove_channel(identifier):
    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM channels WHERE identifier=?", (identifier,))
    c.commit()
    cnt = cur.rowcount
    c.close()
    return cnt

def list_channels():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT identifier FROM channels ORDER BY id ASC")
    rows = [r["identifier"] for r in cur.fetchall()]
    c.close()
    return rows

def add_movie(name, file_id, genre=None, premium=0, added_by=None):
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO movies (name, file_id, genre, premium, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, file_id, genre or "", int(bool(premium)), added_by, datetime.utcnow().isoformat()))
    c.commit()
    mid = cur.lastrowid
    c.close()
    return mid

def delete_movie(mid):
    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM movies WHERE id=?", (mid,))
    c.commit()
    cnt = cur.rowcount
    c.close()
    return cnt

def get_movie(mid):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM movies WHERE id=?", (mid,))
    r = cur.fetchone()
    c.close()
    return dict(r) if r else None

def list_movies(limit=200):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM movies ORDER BY id ASC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    c.close()
    return rows

def inc_view(mid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE movies SET views = views + 1 WHERE id=?", (mid,))
    c.commit()
    c.close()

def like_movie(mid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE movies SET likes = likes + 1 WHERE id=?", (mid,))
    c.commit()
    c.close()

def dislike_movie(mid):
    c = conn()
    cur = c.cursor()
    cur.execute("UPDATE movies SET dislikes = dislikes + 1 WHERE id=?", (mid,))
    c.commit()
    c.close()

def search_movies(q, limit=50):
    q = f"%{q.lower()}%"
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM movies WHERE lower(name) LIKE ? OR lower(genre) LIKE ? LIMIT ?", (q, q, limit))
    rows = [dict(r) for r in cur.fetchall()]
    c.close()
    return rows

def user_subscribed_all(user_id):
    channels = list_channels()
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:
            logger.info("Check channel error %s %s", ch, e)
            missing.append(ch)
    return (len(missing) == 0), missing

def backup_db():
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"bot_db_backup_{ts}.db")
    try:
        shutil.copyfile(DB_FILE, dst)
        logger.info("Backup created: %s", dst)
    except Exception as e:
        logger.exception("Backup failed: %s", e)

# schedule daily backup at 00:00 UTC and daily news at 00:05 UTC
scheduler.add_job(backup_db, "cron", hour=0, minute=0)
# daily_news job defined later; scheduled if news exist

# ---------------- Keyboards ----------------
def main_kb(user_id=None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎲 Tasodifiy kino", "🎞 Kinolar")
    kb.add("🔎 Qidiruv", "📢 Kanallar")
    kb.add("⚙️ Sozlamalar", "ℹ️ Yordam")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/addmovie", "/delmovie")
    kb.add("/addchannel", "/delchannel")
    kb.add("/news_add", "/news_list")
    kb.add("/topmovies", "/stats")
    kb.add("/give_premium", "/revoke_premium")
    kb.add("/addadmin", "/deladmin")
    return kb

# ---------------- Handlers ----------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    add_user_if_new(message.from_user)
    # referral: /start <refid>
    if message.text and message.text.startswith("/start "):
        parts = message.text.split()
        if len(parts) > 1:
            try:
                ref = int(parts[1])
                if ref != message.from_user.id:
                    c = conn()
                    cur = c.cursor()
                    cur.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                                (ref, message.from_user.id, datetime.utcnow().isoformat()))
                    cur.execute("UPDATE users SET referrals = referrals + 1 WHERE id=?", (ref,))
                    c.commit()
                    c.close()
            except:
                pass
    txt = f"👋 Assalomu alaykum, {message.from_user.first_name}!\nKinoTreylerUz_Bot ga xush kelibsiz.\nRaqam yuboring yoki menyudan tanlang."
    bot.send_message(message.chat.id, txt, reply_markup=main_kb())

@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.send_message(message.chat.id, "Yordam: Kino raqamini yuboring yoki /random, /genres, /topmovies (admin), /stats (admin).", reply_markup=main_kb())

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Siz admin emassiz.")
        return
    bot.send_message(message.chat.id, "🔧 Admin panel", reply_markup=admin_kb())

# ---------- Admin: add movie flow ----------
admin_states = {}  # admin_id -> dict state

@bot.message_handler(commands=["addmovie"])
def cmd_addmovie(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat adminlar.")
        return
    admin_states[message.from_user.id] = {"action": "await_name"}
    bot.send_message(message.chat.id, "🎬 Kinoning nomini yuboring (to'liq):")

@bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]["action"]=="await_name", content_types=["text"])
def _addmovie_name(message):
    admin_states[message.from_user.id]["name"] = message.text.strip()
    admin_states[message.from_user.id]["action"] = "await_file"
    bot.send_message(message.chat.id, "Endi video yoki fayl yuboring (video/document/animation):")

@bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]["action"]=="await_file", content_types=["video","document","animation"])
def _addmovie_file(message):
    uid = message.from_user.id
    name = admin_states[uid].get("name", "No name")
    file_id = None
    if message.content_type == "video" and message.video:
        file_id = message.video.file_id
    elif message.content_type == "animation" and message.animation:
        file_id = message.animation.file_id
    elif message.content_type == "document" and message.document:
        file_id = message.document.file_id
    if not file_id:
        bot.send_message(message.chat.id, "❗ Video topilmadi. Jarayon bekor qilindi.")
        admin_states.pop(uid, None)
        return
    admin_states[uid]["file_id"] = file_id
    admin_states[uid]["action"] = "await_genre"
    bot.send_message(message.chat.id, "Janrini yozing (masalan: jangari, komediya):")

@bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]["action"]=="await_genre", content_types=["text"])
def _addmovie_genre(message):
    uid = message.from_user.id
    genre = message.text.strip()
    admin_states[uid]["genre"] = genre
    admin_states[uid]["action"] = "await_premium"
    bot.send_message(message.chat.id, "Agar bu kino PREMIUM bo'lsa 'ha' yozing, aks holda 'yo'q':")

@bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]["action"]=="await_premium", content_types=["text"])
def _addmovie_premium(message):
    uid = message.from_user.id
    ans = message.text.strip().lower()
    premium = 1 if ans in ("ha","yes","y") else 0
    state = admin_states.pop(uid, None)
    if not state:
        bot.send_message(message.chat.id, "Jarayon xatolik bilan yakunlandi.")
        return
    mid = add_movie(state["name"], state["file_id"], state.get("genre"), premium, added_by=uid)
    bot.send_message(message.chat.id, f"✅ Kino qo'shildi. ID: {mid}\nNom: {state['name']}\nJanr: {state.get('genre')}\nPremium: {'Ha' if premium else 'Yo\'q'}")

# ---------- Admin: delete movie ----------
@bot.message_handler(commands=["delmovie"])
def cmd_delmovie(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    movies = list_movies(200)
    if not movies:
        bot.send_message(message.chat.id, "📭 Kinolar yo'q.")
        return
    txt = "🎞 Kinolar:\n" + "\n".join(f"{m['id']}. {m['name']}" for m in movies)
    bot.send_message(message.chat.id, txt)
    bot.send_message(message.chat.id, "O'chirmoqchi bo'lgan ID ni yuboring:")
    bot.register_next_step_handler(message, _delmovie_step)

def _delmovie_step(message):
    try:
        mid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❗ Noto'g'ri ID.")
        return
    cnt = delete_movie(mid)
    if cnt:
        bot.send_message(message.chat.id, f"✅ {mid} o'chirildi.")
    else:
        bot.send_message(message.chat.id, "❌ Bunday ID topilmadi.")

# ---------- Channel management ----------
@bot.message_handler(commands=["addchannel"])
def cmd_addchannel(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "Kanal username yoki chat_id yuboring (masalan: @kanalingiz yoki -100123...):")
    bot.register_next_step_handler(message, _addchannel_step)

def _addchannel_step(message):
    ch = message.text.strip()
    ok = add_channel(ch)
    if ok:
        bot.send_message(message.chat.id, f"✅ Kanal qo'shildi: {ch}")
    else:
        bot.send_message(message.chat.id, "⚠️ Kanal allaqachon mavjud yoki xato.")

@bot.message_handler(commands=["delchannel"])
def cmd_delchannel(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "O'chirish uchun kanal username yoki chat_id yuboring:")
    bot.register_next_step_handler(message, _delchannel_step)

def _delchannel_step(message):
    ch = message.text.strip()
    cnt = remove_channel(ch)
    if cnt:
        bot.send_message(message.chat.id, f"✅ Kanal o'chirildi: {ch}")
    else:
        bot.send_message(message.chat.id, "❌ Kanal topilmadi.")

@bot.message_handler(commands=["channels"])
def cmd_channels(message):
    chs = list_channels()
    if not chs:
        bot.send_message(message.chat.id, "📭 Majburiy kanallar ro'yxati bo'sh.")
        return
    kb = types.InlineKeyboardMarkup()
    for ch in chs:
        if ch.startswith("@"):
            kb.add(types.InlineKeyboardButton(ch, url=f"https://t.me/{ch.lstrip('@')}"))
        else:
            kb.add(types.InlineKeyboardButton(str(ch), callback_data="noop"))
    bot.send_message(message.chat.id, "📢 Majburiy kanallar:", reply_markup=kb)

# ---------- News (daily & manual) ----------
@bot.message_handler(commands=["news_add"])
def cmd_news_add(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "Yangilik turi (text/photo/video) ni yozing:")
    bot.register_next_step_handler(message, _news_kind_step)

def _news_kind_step(message):
    kind = message.text.strip().lower()
    if kind not in ("text","photo","video"):
        bot.send_message(message.chat.id, "❗ Faqat text/photo/video")
        return
    bot.send_message(message.chat.id, "Endi content yuboring (text yoki media fayl):")
    bot.register_next_step_handler(message, _news_content_step, kind)

def _news_content_step(message, kind):
    if kind == "text":
        content = message.text or ""
        add_news_db = True
        c = conn()
        cur = c.cursor()
        cur.execute("INSERT INTO news (kind, content, caption, scheduled, created_at) VALUES (?, ?, ?, ?, ?)",
                    (kind, content, "", 0, datetime.utcnow().isoformat()))
        c.commit(); c.close()
        bot.send_message(message.chat.id, "✅ Yangilik (text) qo'shildi.")
        return
    # for photo/video/document
    file_id = None
    caption = ""
    if message.content_type == "photo":
        file_id = message.photo[-1].file_id
        caption = message.caption or ""
    elif message.content_type == "video":
        file_id = message.video.file_id
        caption = message.caption or ""
    elif message.content_type == "document":
        file_id = message.document.file_id
        caption = message.caption or ""
    else:
        bot.send_message(message.chat.id, "❗ Fayl yuboring.")
        return
    c = conn()
    cur = c.cursor()
    cur.execute("INSERT INTO news (kind, content, caption, scheduled, created_at) VALUES (?, ?, ?, ?, ?)",
                (kind, file_id, caption, 0, datetime.utcnow().isoformat()))
    c.commit(); c.close()
    bot.send_message(message.chat.id, "✅ Yangilik (media) qo'shildi.")

@bot.message_handler(commands=["news_list"])
def cmd_news_list(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM news ORDER BY id DESC")
    rows = cur.fetchall()
    c.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Yangiliklar bo'sh.")
        return
    txt = "📰 Yangiliklar:\n" + "\n".join(f"{r['id']}. {r['kind']} - { (r['caption'] or r['content'])[:40] }" for r in rows)
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "📣 Matn yuboring (broadcas):")
    bot.register_next_step_handler(message, _broadcast_step)

def _broadcast_step(message):
    text = message.text or ""
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM users")
    users = [r["id"] for r in cur.fetchall()]
    c.close()
    count = 0
    for u in users:
        try:
            bot.send_message(u, text)
            count += 1
            time.sleep(0.05)
        except Exception as e:
            logger.info("Broadcast fail %s %s", u, e)
    bot.send_message(message.chat.id, f"✅ Xabar yuborildi: {count} foydalanuvchiga.")

# ---------- Random movie ----------
@bot.message_handler(commands=["random","rand"])
def cmd_random(message):
    movies = list_movies()
    if not movies:
        bot.send_message(message.chat.id, "📭 Kinolar yo'q.")
        return
    movie = random.choice(movies)
    # subscription check
    ok, missing = user_subscribed_all(message.from_user.id)
    if not ok:
        kb = types.InlineKeyboardMarkup()
        for ch in missing:
            if ch.startswith("@"):
                kb.add(types.InlineKeyboardButton(ch, url=f"https://t.me/{ch.lstrip('@')}"))
            else:
                kb.add(types.InlineKeyboardButton(str(ch), callback_data="noop"))
        kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
        bot.send_message(message.chat.id, "⚠️ Avval kanallarga a'zo bo'ling:", reply_markup=kb)
        return
    if movie.get("premium"):
        c = conn()
        cur = c.cursor()
        cur.execute("SELECT is_premium FROM users WHERE id=?", (message.from_user.id,))
        r = cur.fetchone()
        c.close()
        if not r or r["is_premium"] != 1:
            bot.send_message(message.chat.id, "🔒 Bu kino premium. Premium foydalanuvchilar ko'ra oladi.")
            return
    try:
        bot.send_video(message.chat.id, movie["file_id"], caption=f"🎬 {movie['name']}\n\nJanr: {movie['genre']}")
        inc_view(movie["id"])
    except Exception as e:
        logger.exception("Random send error: %s", e)
        bot.send_message(message.chat.id, "Xatolik yuz berdi.")

# ---------- Get by ID ----------
@bot.message_handler(func=lambda m: m.text and m.text.strip().isdigit())
def cmd_get_by_id(message):
    mid = int(message.text.strip())
    movie = get_movie(mid)
    if not movie:
        bot.send_message(message.chat.id, "❌ Bunday ID topilmadi.")
        return
    ok, missing = user_subscribed_all(message.from_user.id)
    if not ok:
        kb = types.InlineKeyboardMarkup()
        for ch in missing:
            if ch.startswith("@"):
                kb.add(types.InlineKeyboardButton(ch, url=f"https://t.me/{ch.lstrip('@')}"))
            else:
                kb.add(types.InlineKeyboardButton(str(ch), callback_data="noop"))
        kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
        bot.send_message(message.chat.id, "⚠️ Avval kanallarga a'zo bo'ling:", reply_markup=kb)
        return
    if movie.get("premium"):
        c = conn()
        cur = c.cursor()
        cur.execute("SELECT is_premium FROM users WHERE id=?", (message.from_user.id,))
        r = cur.fetchone()
        c.close()
        if not r or r["is_premium"] != 1:
            bot.send_message(message.chat.id, "🔒 Bu kino premium. Premium foydalanuvchilar ko'ra oladi.")
            return
    try:
        bot.send_video(message.chat.id, movie["file_id"], caption=f"🎬 {movie['name']}\n\nJanr: {movie['genre']}")
        inc_view(mid)
    except Exception as e:
        logger.exception("Send movie error: %s", e)
        bot.send_message(message.chat.id, "Xatolik yuz berdi.")

# ---------- Search ----------
@bot.message_handler(func=lambda m: m.text and len(m.text.strip())>1 and not m.text.strip().isdigit())
def cmd_search(message):
    q = message.text.strip()
    rows = search_movies(q)
    if not rows:
        bot.send_message(message.chat.id, "🔍 Hech narsa topilmadi.")
        return
    kb = types.InlineKeyboardMarkup()
    for r in rows[:20]:
        kb.add(types.InlineKeyboardButton(f"{r['id']}. {r['name'][:40]}", callback_data=f"get_{r['id']}"))
    bot.send_message(message.chat.id, f"🔎 Topildi {len(rows)} ta natija:", reply_markup=kb)

# ---------- Callback queries (rating, get, check_subs, like/dislike) ----------
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    data = call.data or ""
    uid = call.from_user.id
    if data == "check_subs":
        ok, missing = user_subscribed_all(uid)
        if ok:
            bot.answer_callback_query(call.id, "✅ A'zo bo'lgansiz")
            bot.send_message(uid, "🎉 Rahmat! Endi kinoning raqamini yuboring.")
        else:
            bot.answer_callback_query(call.id, "❌ Hali ham a'zo emassiz.")
        return
    if data.startswith("get_"):
        try:
            mid = int(data.split("_",1)[1])
        except:
            bot.answer_callback_query(call.id, "Xato ID.")
            return
        movie = get_movie(mid)
        if not movie:
            bot.answer_callback_query(call.id, "Kino topilmadi.")
            return
        ok, missing = user_subscribed_all(uid)
        if not ok:
            bot.answer_callback_query(call.id, "Avval kanallarga a'zo bo'ling.", show_alert=True)
            return
        if movie.get("premium"):
            c = conn()
            cur = c.cursor()
            cur.execute("SELECT is_premium FROM users WHERE id=?", (uid,))
            r = cur.fetchone()
            c.close()
            if not r or r["is_premium"] != 1:
                bot.answer_callback_query(call.id, "Bu kino premium.", show_alert=True)
                return
        try:
            bot.send_video(uid, movie["file_id"], caption=f"🎬 {movie['name']}\n\nJanr: {movie['genre']}")
            inc_view(mid)
            # after sending, add like/dislike buttons
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("👍 Yoqdi", callback_data=f"like_{mid}"),
                   types.InlineKeyboardButton("👎 Yoqmadi", callback_data=f"dislike_{mid}"))
            bot.send_message(uid, "Filmni baholang:", reply_markup=kb)
            bot.answer_callback_query(call.id, "Kino yuborildi.")
        except Exception as e:
            logger.exception("Callback send error: %s", e)
            bot.answer_callback_query(call.id, "Xatolik yuz berdi.")
        return
    if data.startswith("like_"):
        try:
            mid = int(data.split("_",1)[1])
        except:
            bot.answer_callback_query(call.id, "Xato.")
            return
        like_movie(mid)
        bot.answer_callback_query(call.id, "Rahmat! Baho qabul qilindi.")
        return
    if data.startswith("dislike_"):
        try:
            mid = int(data.split("_",1)[1])
        except:
            bot.answer_callback_query(call.id, "Xato.")
            return
        dislike_movie(mid)
        bot.answer_callback_query(call.id, "Fikr uchun rahmat.")
        return
    if data == "noop":
        bot.answer_callback_query(call.id, "Bu tugma ishlamaydi.")
        return

# ---------- Genres ----------
@bot.message_handler(commands=["genres"])
def cmd_genres(message):
    # show known genres
    movies = list_movies(500)
    genres = sorted({(m.get("genre") or "").strip().lower() for m in movies if m.get("genre")})
    if not genres:
        bot.send_message(message.chat.id, "📭 Hozircha janrlar mavjud emas.")
        return
    kb = types.InlineKeyboardMarkup()
    for g in genres:
        kb.add(types.InlineKeyboardButton(g.title(), callback_data=f"genre_{g}"))
    bot.send_message(message.chat.id, "🎭 Janrlarni tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("genre_"))
def genre_callback(call):
    g = call.data.split("_",1)[1]
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM movies WHERE lower(genre)=? LIMIT 100", (g.lower(),))
    rows = cur.fetchall()
    c.close()
    if not rows:
        bot.answer_callback_query(call.id, "Bu janrda film topilmadi.")
        return
    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(f"{r['id']}. {r['name'][:40]}", callback_data=f"get_{r['id']}"))
    bot.send_message(call.from_user.id, f"🎞 {g.title()} janridagi kinolar:", reply_markup=kb)
    bot.answer_callback_query(call.id, "Janr natijalari yuborildi.")

# ---------- Top movies graph / stats (admin) ----------
@bot.message_handler(commands=["topmovies"])
def cmd_topmovies(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT name, views FROM movies ORDER BY views DESC LIMIT 10")
    rows = cur.fetchall()
    c.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Hech qanday ma'lumot yo'q.")
        return
    names = [r["name"][:30] for r in rows]
    views = [r["views"] for r in rows]
    plt.figure(figsize=(8,4))
    plt.barh(range(len(names))[::-1], views[::-1])
    plt.yticks(range(len(names))[::-1], names[::-1])
    plt.xlabel("Ko'rishlar soni")
    plt.title("Top 10 ko'p ko'rilgan kinolar")
    img_path = f"topmovies_{int(time.time())}.png"
    plt.tight_layout()
    plt.savefig(img_path)
    plt.close()
    with open(img_path, "rb") as f:
        bot.send_photo(message.chat.id, f, caption="📊 Top 10")
    os.remove(img_path)

@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    users_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM movies")
    movies_cnt = cur.fetchone()["cnt"]
    cur.close(); c.close()
    bot.send_message(message.chat.id, f"👥 Foydalanuvchilar: {users_cnt}\n🎞 Kinolar: {movies_cnt}\n📁 Backup papka: {BACKUP_DIR}")

# ---------- Give/Revoke premium ----------
@bot.message_handler(commands=["give_premium"])
def cmd_give_premium(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "User ID ni yuboring (premium berish uchun):")
    bot.register_next_step_handler(message, _give_premium_step)

def _give_premium_step(message):
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❗ Noto'g'ri ID.")
        return
    set_user_premium(uid, 1)
    bot.send_message(message.chat.id, f"✅ {uid} ga premium berildi.")

@bot.message_handler(commands=["revoke_premium"])
def cmd_revoke_premium(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Faqat admin.")
        return
    bot.send_message(message.chat.id, "User ID ni yuboring (premium olib tashlash uchun):")
    bot.register_next_step_handler(message, _revoke_premium_step)

def _revoke_premium_step(message):
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❗ Noto'g'ri ID.")
        return
    set_user_premium(uid, 0)
    bot.send_message(message.chat.id, f"✅ {uid} premium olib tashlandi.")

# ---------- Admin add/del admin ----------
@bot.message_handler(commands=["addadmin"])
def cmd_addadmin(message):
    if message.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Faqat MAIN admin.")
        return
    bot.send_message(message.chat.id, "Qo'shmoqchi bo'lgan admin ID ni yuboring:")
    bot.register_next_step_handler(message, _addadmin_step)

def _addadmin_step(message):
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❗ Noto'g'ri ID.")
        return
    add_admin(uid)
    bot.send_message(message.chat.id, f"✅ {uid} admin qilindi.")

@bot.message_handler(commands=["deladmin"])
def cmd_deladmin(message):
    if message.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Faqat MAIN admin.")
        return
    bot.send_message(message.chat.id, "O'chirmoqchi bo'lgan admin ID ni yuboring:")
    bot.register_next_step_handler(message, _deladmin_step)

def _deladmin_step(message):
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❗ Noto'g'ri ID.")
        return
    remove_admin(uid)
    bot.send_message(message.chat.id, f"✅ {uid} adminlikdan olib tashlandi.")

# ---------- Give referral info ----------
@bot.message_handler(commands=["referral"])
def cmd_referral(message):
    bot.send_message(message.chat.id, f"Sizning referal havolangiz:\nhttps://t.me/{bot.get_me().username}?start={message.from_user.id}")

@bot.message_handler(commands=["referrals"])
def cmd_referrals(message):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT referrals FROM users WHERE id=?", (message.from_user.id,))
    r = cur.fetchone()
    c.close()
    if not r:
        bot.send_message(message.chat.id, "Siz haqida ma'lumot topilmadi.")
        return
    bot.send_message(message.chat.id, f"Siz taklif qilganlar soni: {r['referrals']}")

# ---------- Webhook endpoints ----------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        logger.exception("Webhook error: %s", e)
    return Response("OK", status=200)

@app.route("/", methods=["GET"])
def index():
    return "<b>KinoTreylerUz_Bot — isRunning</b>"

# ---------- Set webhook ----------
def set_webhook():
    url = WEBHOOK_URL.rstrip("/") + "/" + TOKEN
    try:
        bot.remove_webhook()
    except:
        pass
    try:
        res = bot.set_webhook(url=url)
        logger.info("set_webhook result: %s", res)
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)

# ---------- Daily news job ----------
def daily_news_job():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM news WHERE scheduled=1 ORDER BY id ASC")
    rows = cur.fetchall()
    if not rows:
        # take latest non-scheduled news
        cur.execute("SELECT * FROM news ORDER BY id DESC LIMIT 1")
        rows = cur.fetchall()
    users = []
    cur.execute("SELECT id FROM users")
    users = [r["id"] for r in cur.fetchall()]
    for item in rows:
        kind = item["kind"]
        content = item["content"]
        caption = item["caption"] or ""
        for u in users:
            try:
                if kind == "text":
                    bot.send_message(u, caption or content)
                elif kind == "photo":
                    bot.send_photo(u, content, caption=caption)
                elif kind == "video":
                    bot.send_video(u, content, caption=caption)
                time.sleep(0.05)
            except Exception as e:
                logger.info("Daily news send failed for %s: %s", u, e)
    c.close()

scheduler.add_job(daily_news_job, "cron", hour=0, minute=5)

# ---------- Start main ----------
if __name__ == "__main__":
    init_db()
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
