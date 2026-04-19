import asyncio
import logging
import os
import json
from collections import defaultdict

import aiohttp
import asyncpg
from aiohttp import web
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

pool = None

# ================= DB =================
async def init_db():
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            name TEXT,
            poster TEXT,
            tvmaze_id INTEGER,
            episodes_json TEXT
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS watched (
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

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        INSERT INTO series (user_id, name, poster, tvmaze_id, episodes_json)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """, (
            m.from_user.id,
            show["name"],
            show.get("image", {}).get("original"),
            show["id"],
            json.dumps(episodes)
        ))

        series_id = row["id"]

        # старые сезоны → просмотрены
        for season, total in episodes.items():
            season = int(season)

            if season < last_season:
                for ep in range(1, total + 1):
                    await conn.execute("""
                    INSERT INTO watched (series_id, season, episode)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """, (series_id, season, ep))

    await m.answer(f"✅ Добавлен: {show['name']}")

# ================= API SERVER =================
async def api_series(request):
    user_id = request.query.get("user_id")

    if not user_id:
        return web.json_response([])

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
        SELECT id, name, poster FROM series WHERE user_id=$1
        """, int(user_id))

    return web.json_response([
        {"id": r["id"], "name": r["name"], "poster": r["poster"]}
        for r in rows
    ])


async def api_series_detail(request):
    series_id = request.query.get("series_id")

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT name, poster, episodes_json FROM series WHERE id=$1
        """, int(series_id))

        episodes = json.loads(row["episodes_json"])

        watched_rows = await conn.fetch("""
        SELECT season, episode FROM watched WHERE series_id=$1
        """, int(series_id))

    watched_map = {}
    for r in watched_rows:
        watched_map.setdefault(r["season"], set()).add(r["episode"])

    seasons = []

    for season, total in episodes.items():
        season = int(season)

        seasons.append({
            "season": season,
            "total": total,
            "watched": list(watched_map.get(season, []))
        })

    return web.json_response({
        "name": row["name"],
        "poster": row["poster"],
        "seasons": sorted(seasons, key=lambda x: x["season"])
    })


async def toggle_episode(request):
    data = await request.json()

    async with pool.acquire() as conn:
        exists = await conn.fetchrow("""
        SELECT 1 FROM watched
        WHERE series_id=$1 AND season=$2 AND episode=$3
        """, data["series_id"], data["season"], data["episode"])

        if exists:
            await conn.execute("""
            DELETE FROM watched
            WHERE series_id=$1 AND season=$2 AND episode=$3
            """, data["series_id"], data["season"], data["episode"])
        else:
            await conn.execute("""
            INSERT INTO watched (series_id, season, episode)
            VALUES ($1, $2, $3)
            """, data["series_id"], data["season"], data["episode"])

    return web.json_response({"ok": True})


async def delete_series(request):
    data = await request.json()

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM series WHERE id=$1", data["series_id"])
        await conn.execute("DELETE FROM watched WHERE series_id=$1", data["series_id"])

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
    global pool

    pool = await asyncpg.create_pool(DATABASE_URL)

    await init_db()

    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
