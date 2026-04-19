import asyncio
import logging
import sqlite3
import os
import json
from collections import defaultdict

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

if not BASE_URL:
    raise ValueError("BASE_URL missing")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "db.sqlite")

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
            tvmaze_id INTEGER,
            episodes_json TEXT
        );

        CREATE TABLE IF NOT EXISTS watched (
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        );
        """)
        conn.commit()

# ================= API =================
async def get_tvmaze(query):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/search/shows?q={query}") as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data[0]["show"] if data else None

async def get_episodes_map(tvmaze_id):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/shows/{tvmaze_id}/episodes") as r:
            if r.status != 200:
                return {}
            data = await r.json()

    result = defaultdict(int)
    for ep in data:
        if ep.get("season"):
            result[ep["season"]] += 1
    return dict(result)

# ================= BOT =================
@dp.message(Command("start"))
async def start(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Открыть Netflix",
            web_app=WebAppInfo(url=BASE_URL)
        )]
    ])
    await m.answer("Добро пожаловать 🍿", reply_markup=kb)


@dp.message(Command("add"))
async def add(m: types.Message):
    query = m.text.replace("/add", "").strip()

    if not query:
        await m.answer("Напиши: /add Breaking Bad")
        return

    show = await get_tvmaze(query)

    if not show:
        await m.answer("Не найдено")
        return

    episodes = await get_episodes_map(show["id"])

    if not episodes:
        await m.answer("Нет данных по сериям")
        return

    last_season = max(map(int, episodes.keys()))

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO series (user_id, name, poster, tvmaze_id, episodes_json)
        VALUES (?, ?, ?, ?, ?)
        """, (
            m.from_user.id,
            show["name"],
            show.get("image", {}).get("original"),
            show["id"],
            json.dumps(episodes)
        ))

        series_id = cur.lastrowid

        # ✅ все прошлые сезоны → просмотрены
        for season, total in episodes.items():
            season = int(season)

            if season < last_season:
                for ep in range(1, total + 1):
                    cur.execute("""
                    INSERT OR IGNORE INTO watched (series_id, season, episode)
                    VALUES (?, ?, ?)
                    """, (series_id, season, ep))

        conn.commit()

    await m.answer(f"✅ Добавлен: {show['name']}")


# ================= API SERVER =================
async def api_series(request):
    user_id = request.query.get("user_id")

    if not user_id:
        return web.json_response([])

    user_id = int(user_id)

    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id,name,poster FROM series WHERE user_id=?", (user_id,))
        rows = cur.fetchall()

    return web.json_response([
        {"id": r[0], "name": r[1], "poster": r[2]}
        for r in rows
    ])


async def api_series_detail(request):
    series_id = request.query.get("series_id")

    if not series_id:
        return web.json_response({"error": "no id"})

    with db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT name, poster, episodes_json FROM series WHERE id=?", (series_id,))
        row = cur.fetchone()

        if not row:
            return web.json_response({"error": "not found"})

        name, poster, episodes_json = row
        episodes = json.loads(episodes_json)

        cur.execute("SELECT season, episode FROM watched WHERE series_id=?", (series_id,))
        watched = cur.fetchall()

    watched_map = {}
    for s, e in watched:
        watched_map.setdefault(s, set()).add(e)

    seasons = []

    for season, total in episodes.items():
        season = int(season)

        seasons.append({
            "season": season,
            "total": total,
            "watched": list(watched_map.get(season, []))
        })

    return web.json_response({
        "name": name,
        "poster": poster,
        "seasons": sorted(seasons, key=lambda x: x["season"])
    })


async def toggle_episode(request):
    data = await request.json()

    series_id = data["series_id"]
    season = data["season"]
    episode = data["episode"]

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT 1 FROM watched WHERE series_id=? AND season=? AND episode=?
        """, (series_id, season, episode))

        exists = cur.fetchone()

        if exists:
            cur.execute("""
            DELETE FROM watched WHERE series_id=? AND season=? AND episode=?
            """, (series_id, season, episode))
        else:
            cur.execute("""
            INSERT INTO watched (series_id, season, episode)
            VALUES (?, ?, ?)
            """, (series_id, season, episode))

        conn.commit()

    return web.json_response({"ok": True})


async def delete_series(request):
    data = await request.json()
    series_id = data["series_id"]

    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM series WHERE id=?", (series_id,))
        cur.execute("DELETE FROM watched WHERE series_id=?", (series_id,))
        conn.commit()

    return web.json_response({"ok": True})


# ================= WEB =================
async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series_detail", api_series_detail)

    app.router.add_post("/api/toggle", toggle_episode)
    app.router.add_post("/api/delete", delete_series)

    app.router.add_static("/static/", path="./web", name="static")

    async def index(request):
        return web.FileResponse("./web/index.html")

    app.router.add_get("/", index)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    print("🌐 WebApp запущен")


# ================= MAIN =================
async def main():
    init_db()
    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
