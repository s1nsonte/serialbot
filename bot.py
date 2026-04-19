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

db_pool = None

# ================= DB =================

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
            tvmaze_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        );

        CREATE TABLE IF NOT EXISTS watched (
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        );
        """)

# ================= API TV =================

async def get_tvmaze(query):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/search/shows?q={query}") as r:
            data = await r.json()
            return data[0]["show"] if data else None

async def get_episodes(tvmaze_id):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/shows/{tvmaze_id}/episodes") as r:
            return await r.json()

# ================= BOT =================

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Открыть",
            web_app=WebAppInfo(url=BASE_URL)
        )]
    ])
    await m.answer("Открывай 👇", reply_markup=kb)

@dp.message(Command("add"))
async def add(m: types.Message):
    query = m.text.replace("/add", "").strip()

    show = await get_tvmaze(query)
    if not show:
        await m.answer("Не найдено")
        return

    episodes = await get_episodes(show["id"])

    async with db_pool.acquire() as conn:
        series_id = await conn.fetchval("""
            INSERT INTO series (user_id, name, poster, tvmaze_id)
            VALUES ($1,$2,$3,$4)
            RETURNING id
        """, m.from_user.id, show["name"], show.get("image", {}).get("original"), show["id"])

        # записываем все серии
        for ep in episodes:
            await conn.execute("""
                INSERT INTO episodes (series_id, season, episode)
                VALUES ($1,$2,$3)
                ON CONFLICT DO NOTHING
            """, series_id, ep["season"], ep["number"])

    await m.answer(f"✅ Добавлен: {show['name']}")

# ================= API =================

async def api_series(request):
    user_id = int(request.query.get("user_id"))

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM series WHERE user_id=$1
        """, user_id)

        result = []

        for r in rows:
            episodes = await conn.fetch("""
                SELECT season, episode FROM episodes
                WHERE series_id=$1
            """, r["id"])

            watched = await conn.fetch("""
                SELECT season, episode FROM watched
                WHERE series_id=$1
            """, r["id"])

            total = len(episodes)
            watched_count = len(watched)

            result.append({
                "id": r["id"],
                "name": r["name"],
                "poster": r["poster"],
                "progress": watched_count,
                "total": total
            })

    return web.json_response(result)

# ================= DETAIL =================

async def api_series_detail(request):
    series_id = int(request.query.get("series_id"))

    async with db_pool.acquire() as conn:
        series = await conn.fetchrow("""
            SELECT * FROM series WHERE id=$1
        """, series_id)

        episodes = await conn.fetch("""
            SELECT season, episode FROM episodes
            WHERE series_id=$1
            ORDER BY season, episode
        """, series_id)

        watched = await conn.fetch("""
            SELECT season, episode FROM watched
            WHERE series_id=$1
        """, series_id)

    watched_set = {(w["season"], w["episode"]) for w in watched}

    seasons = defaultdict(list)

    for ep in episodes:
        seasons[ep["season"]].append({
            "episode": ep["episode"],
            "watched": (ep["season"], ep["episode"]) in watched_set
        })

    return web.json_response({
        "id": series["id"],
        "name": series["name"],
        "poster": series["poster"],
        "seasons": seasons
    })

# ================= TOGGLE =================

async def toggle_episode(request):
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
                VALUES ($1,$2,$3)
            """, series_id, season, episode)

    return web.json_response({"ok": True})

# ================= WEB =================

async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series_detail", api_series_detail)
    app.router.add_post("/api/toggle_episode", toggle_episode)

    app.router.add_static("/static/", path="./web", name="static")

    async def index(request):
        return web.FileResponse("./web/index.html")

    app.router.add_get("/", index)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ================= MAIN =================

async def main():
    await init_db()
    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
