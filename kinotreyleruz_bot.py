import telebot
from flask import Flask, request
import json, os

# === Sozlamalar ===
TOKEN = "7928013094:AAGlDJfmjmJh_xLV3t3drzCMVnDT7tpv7ws"  # <--- Bot tokeningizni shu yerga yozasiz
ADMIN_ID = 912998145           # <--- O'z Telegram ID'ingizni yozasiz
WEBHOOK_URL = "https://your-app-name.onrender.com"  # <--- Keyin Render linkini shu yerga yozasiz

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

MOVIES_FILE = "movies.json"
CHANNELS_FILE = "channels.json"
STATS_FILE = "stats.json"

def load_data(file, default):
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=4)
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

movies = load_data(MOVIES_FILE, [])
channels = load_data(CHANNELS_FILE, [])
stats = load_data(STATS_FILE, {"users": []})

def add_user(user_id):
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_data(STATS_FILE, stats)

# === Start komandasi ===
@bot.message_handler(commands=["start"])
def start(message):
    add_user(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🎬 *KinoTreylerUz_Bot* ga xush kelibsiz!\n\n"
        "Raqam yuboring (masalan: 1) — bot shu raqamdagi kinoni yuboradi.\n\n"
        "🛠 Buyruqlar:\n"
        "/admin — admin panel\n"
        "/channels — majburiy kanallar\n",
        parse_mode="Markdown"
    )

# === Admin panel ===
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "🔐 *Admin panel:*\n"
            "/addmovie — yangi kino qo‘shish\n"
            "/delmovie — kino o‘chirish\n"
            "/addchannel — majburiy kanal qo‘shish\n"
            "/channels — kanallar ro‘yxati\n"
            "/stats — foydalanuvchilar soni",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "🚫 Siz admin emassiz.")

# === Kino qo‘shish ===
@bot.message_handler(commands=["addmovie"])
def add_movie(message):
    if message.chat.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "🚫 Siz admin emassiz.")
    bot.send_message(message.chat.id, "🎥 Kino nomini yuboring:")
    bot.register_next_step_handler(message, get_movie_name)

def get_movie_name(message):
    name = message.text
    bot.send_message(message.chat.id, "📽 Endi kino videosini yuboring:")
    bot.register_next_step_handler(message, lambda msg: save_movie(msg, name))

def save_movie(message, name):
    if not message.video:
        return bot.send_message(message.chat.id, "❌ Video yuborish kerak.")
    movies = load_data(MOVIES_FILE, [])
    movie_id = len(movies) + 1
    movies.append({"id": movie_id, "name": name, "file_id": message.video.file_id})
    save_data(MOVIES_FILE, movies)
    bot.send_message(message.chat.id, f"✅ Kino qo‘shildi: *{name}* (ID: {movie_id})", parse_mode="Markdown")

# === Kino o‘chirish ===
@bot.message_handler(commands=["delmovie"])
def del_movie(message):
    if message.chat.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "🚫 Siz admin emassiz.")
    movies = load_data(MOVIES_FILE, [])
    if not movies:
        return bot.send_message(message.chat.id, "🎬 Hech qanday kino yo‘q.")
    text = "\n".join([f"{m['id']}. {m['name']}" for m in movies])
    bot.send_message(message.chat.id, f"🗑 Qaysi kinoni o‘chirmoqchisiz?\n\n{text}")
    bot.register_next_step_handler(message, confirm_delete)

def confirm_delete(message):
    try:
        num = int(message.text)
        movies = load_data(MOVIES_FILE, [])
        movies = [m for m in movies if m["id"] != num]
        for i, m in enumerate(movies):
            m["id"] = i + 1
        save_data(MOVIES_FILE, movies)
        bot.send_message(message.chat.id, "✅ Kino o‘chirildi.")
    except:
        bot.send_message(message.chat.id, "❌ Xato raqam.")

# === Kanal qo‘shish ===
@bot.message_handler(commands=["addchannel"])
def add_channel(message):
    if message.chat.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "🚫 Siz admin emassiz.")
    bot.send_message(message.chat.id, "📢 Kanal username'ini yuboring (masalan: @KinoTreylerUz)")
    bot.register_next_step_handler(message, save_channel)

def save_channel(message):
    username = message.text.strip()
    channels = load_data(CHANNELS_FILE, [])
    if username not in channels:
        channels.append(username)
        save_data(CHANNELS_FILE, channels)
        bot.send_message(message.chat.id, f"✅ Kanal qo‘shildi: {username}")
    else:
        bot.send_message(message.chat.id, "⚠️ Bu kanal allaqachon mavjud.")

# === Kanal ro‘yxati ===
@bot.message_handler(commands=["channels"])
def show_channels(message):
    channels = load_data(CHANNELS_FILE, [])
    if not channels:
        bot.send_message(message.chat.id, "📭 Hozircha majburiy kanal yo‘q.")
    else:
        text = "\n".join(channels)
        bot.send_message(message.chat.id, f"📢 Majburiy kanallar:\n{text}")

# === Statistika ===
@bot.message_handler(commands=["stats"])
def stats_command(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(message.chat.id, f"👥 Foydalanuvchilar soni: {len(stats['users'])}")
    else:
        bot.send_message(message.chat.id, "🚫 Siz admin emassiz.")

# === Foydalanuvchi raqam yuborsa kino yuborish ===
@bot.message_handler(func=lambda m: m.text and m.text.isdigit())
def send_movie(message):
    user_id = message.chat.id
    channels = load_data(CHANNELS_FILE, [])
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                raise Exception()
        except:
            text = "🚫 Avval quyidagi kanallarga a’zo bo‘ling:\n\n"
            text += "\n".join(channels)
            return bot.send_message(message.chat.id, text)
    movies = load_data(MOVIES_FILE, [])
    num = int(message.text)
    movie = next((m for m in movies if m["id"] == num), None)
    if movie:
        bot.send_video(message.chat.id, movie["file_id"], caption=movie["name"])
    else:
        bot.send_message(message.chat.id, "❌ Bunday raqamdagi kino topilmadi.")

# === Flask Webhook server ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/", methods=["GET"])
def index():
    return "✅ KinoTreylerUz_Bot Webhook ishga tushdi."

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
