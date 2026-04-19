import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from collections import defaultdict
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
TMDB_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing")
if not BASE_URL:
    raise ValueError("BASE_URL missing")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "db.sqlite"

# ================= DB =================

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db() as conn:
        cur = conn.cursor()

        cur.executescript("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            poster TEXT,
            tmdb_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            air_date TEXT
        );

        CREATE TABLE IF NOT EXISTS watched (
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        );
        """)
        conn.commit()

# ================= TMDB =================

async def tmdb_search(query):
    async with aiohttp.ClientSession() as s:
        url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_KEY}&query={query}"
        async with s.get(url) as r:
            data = await r.json()
            return data["results"][0] if data["results"] else None

async def tmdb_episodes(tmdb_id):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_KEY}") as r:
            show = await r.json()

        episodes = []

        for season in show.get("seasons", []):
            num = season["season_number"]

            async with s.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{num}?api_key={TMDB_KEY}") as r:
                data = await r.json()

                for ep in data.get("episodes", []):
                    episodes.append({
                        "season": num,
                        "episode": ep["episode_number"],
                        "air_date": ep.get("air_date")
                    })

        return episodes

# ================= BOT =================

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Открыть",
            web_app=WebAppInfo(url=BASE_URL)
        )]
    ])
    await m.answer("Открывай приложение 👇", reply_markup=kb)

@dp.message(Command("add"))
async def add(m: types.Message):
    query = m.text.replace("/add", "").strip()

    show = await tmdb_search(query)
    if not show:
        await m.answer("Не найдено")
        return

    episodes = await tmdb_episodes(show["id"])

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO series (user_id, name, poster, tmdb_id)
        VALUES (?, ?, ?, ?)
        """, (
            m.from_user.id,
            show["name"],
            f"https://image.tmdb.org/t/p/w500{show['poster_path']}" if show.get("poster_path") else None,
            show["id"]
        ))

        series_id = cur.lastrowid

        now = datetime.now()

        for ep in episodes:
            cur.execute("""
            INSERT INTO episodes (series_id, season, episode, air_date)
            VALUES (?, ?, ?, ?)
            """, (
                series_id,
                ep["season"],
                ep["episode"],
                ep["air_date"]
            ))

            if ep["air_date"]:
                air = datetime.fromisoformat(ep["air_date"])
                if air <= now:
                    cur.execute("""
                    INSERT OR IGNORE INTO watched (series_id, season, episode)
                    VALUES (?, ?, ?)
                    """, (series_id, ep["season"], ep["episode"]))

        conn.commit()

    await m.answer(f"✅ Добавлен: {show['name']}")

# ================= API =================

async def api_series(request):
    user_id = request.query.get("user_id")
    if not user_id:
        return web.json_response([])

    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id,name,poster FROM series WHERE user_id=?", (user_id,))
        rows = cur.fetchall()

    return web.json_response([
        {"id": r[0], "name": r[1], "poster": r[2]}
        for r in rows
    ])

async def api_detail(request):
    series_id = request.query.get("id")

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT season, episode FROM watched WHERE series_id=?
        """, (series_id,))
        watched = set(cur.fetchall())

        cur.execute("""
        SELECT season, episode, air_date
        FROM episodes
        WHERE series_id=?
        ORDER BY season, episode
        """, (series_id,))
        rows = cur.fetchall()

    data = []

    for s, e, air in rows:
        data.append({
            "season": s,
            "episode": e,
            "watched": (s, e) in watched
        })

    return web.json_response(data)

async def api_watch(request):
    series_id = request.query.get("series_id")
    season = request.query.get("season")
    episode = request.query.get("episode")

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT OR IGNORE INTO watched (series_id, season, episode)
        VALUES (?, ?, ?)
        """, (series_id, season, episode))
        conn.commit()

    return web.json_response({"ok": True})

# ================= WEB =================

async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/detail", api_detail)
    app.router.add_get("/api/watch", api_watch)

    app.router.add_static("/static/", path="./web")

    async def index(request):
        return web.FileResponse("./web/index.html")

    app.router.add_get("/", index)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ================= MAIN =================

async def main():
    init_db()
    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
