import asyncio
import logging
import os
import json
from collections import defaultdict

import aiohttp
from aiohttp import web
import asyncpg

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

if not BASE_URL:
    raise ValueError("BASE_URL missing")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL missing")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DB =================
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            name TEXT,
            poster TEXT,
            tvmaze_id INTEGER,
            episodes_json JSONB
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS watched (
            id SERIAL PRIMARY KEY,
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        );
        """)

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
            text="🎬 Открыть приложение",
            web_app=WebAppInfo(url=BASE_URL)
        )]
    ])
    await m.answer("Добро пожаловать!", reply_markup=kb)

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

    async with db_pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO series (user_id, name, poster, tvmaze_id, episodes_json)
        VALUES ($1, $2, $3, $4, $5)
        """,
        m.from_user.id,
        show["name"],
        (show.get("image") or {}).get("original"),
        show["id"],
        json.dumps(episodes)
        )

    await m.answer(f"✅ Добавлен: {show['name']}")

@dp.message(Command("delete"))
async def delete(m: types.Message):
    query = m.text.replace("/delete", "").strip()

    if not query:
        await m.answer("Напиши: /delete Название")
        return

    async with db_pool.acquire() as conn:
        result = await conn.execute("""
        DELETE FROM series
        WHERE user_id=$1 AND LOWER(name)=LOWER($2)
        """, m.from_user.id, query)

    await m.answer("🗑 Удалено (если найдено)")

# ================= API SERVER =================
async def api_series(request):
    user_id = request.query.get("user_id")

    if not user_id:
        return web.json_response([])

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, name, poster, episodes_json
        FROM series
        WHERE user_id=$1
        """, int(user_id))

    result = []
    for r in rows:
        episodes = r["episodes_json"] or {}
        total = sum(episodes.values())

        result.append({
            "id": r["id"],
            "name": r["name"],
            "poster": r["poster"],
            "episodes": episodes,
            "total": total
        })

    return web.json_response(result)

async def api_series_detail(request):
    series_id = request.query.get("series_id")

    if not series_id:
        return web.json_response({})

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT * FROM series WHERE id=$1
        """, int(series_id))

        watched = await conn.fetch("""
        SELECT season, episode FROM watched WHERE series_id=$1
        """, int(series_id))

    watched_map = {(w["season"], w["episode"]) for w in watched}

    return web.json_response({
        "id": row["id"],
        "name": row["name"],
        "poster": row["poster"],
        "episodes": row["episodes_json"],
        "watched": list(watched_map)
    })

async def api_toggle(request):
    data = await request.json()

    series_id = data["series_id"]
    season = data["season"]
    episode = data["episode"]

    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow("""
        SELECT 1 FROM watched
        WHERE series_id=$1 AND season=$2 AND episode=$3
        """, series_id, season, episode)

        if exists:
            await conn.execute("""
            DELETE FROM watched
            WHERE series_id=$1 AND season=$2 AND episode=$3
            """, series_id, season, episode)
        else:
            await conn.execute("""
            INSERT INTO watched (series_id, season, episode)
            VALUES ($1, $2, $3)
            """, series_id, season, episode)

    return web.json_response({"ok": True})

# ================= WEB =================
async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series_detail", api_series_detail)
    app.router.add_post("/api/toggle", api_toggle)

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
    await init_db()

    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
