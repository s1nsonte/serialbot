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

DB_PATH = "./data.db"


# ================= DB =================

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            poster TEXT,
            tvmaze_id INTEGER,
            episodes_json TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS watched (
            series_id INTEGER,
            season INTEGER,
            episode INTEGER,
            UNIQUE(series_id, season, episode)
        )
        """)

        conn.commit()


# ================= TVMAZE =================

async def get_tvmaze(query):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/search/shows?q={query}") as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data[0]["show"] if data else None


async def get_episodes(tvmaze_id):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.tvmaze.com/shows/{tvmaze_id}/episodes") as r:
            if r.status != 200:
                return []
            return await r.json()


def build_season_map(episodes):
    result = defaultdict(list)

    for ep in episodes:
        if ep.get("season") and ep.get("number"):
            result[ep["season"]].append({
                "episode": ep["number"],
                "name": ep["name"],
                "airdate": ep["airdate"]
            })

    return dict(result)


# ================= BOT =================

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Открыть",
            web_app=WebAppInfo(url=BASE_URL)
        )]
    ])
    await m.answer("Сериалы 👇", reply_markup=kb)


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

    episodes = await get_episodes(show["id"])
    season_map = build_season_map(episodes)

    if not season_map:
        await m.answer("Нет данных по сериям")
        return

    last_season = max(map(int, season_map.keys()))

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO series (user_id, name, poster, tvmaze_id, episodes_json)
        VALUES (?, ?, ?, ?, ?)
        """, (
            m.from_user.id,
            show["name"],
            (show.get("image") or {}).get("original"),
            show["id"],
            json.dumps(season_map)
        ))

        series_id = cur.lastrowid

        # 🔥 Автоматически отмечаем ВСЕ прошлые сезоны как просмотренные
        for season, eps in season_map.items():
            if int(season) < last_season:
                for ep in eps:
                    cur.execute("""
                    INSERT OR IGNORE INTO watched(series_id, season, episode)
                    VALUES (?, ?, ?)
                    """, (series_id, int(season), ep["episode"]))

        conn.commit()

    await m.answer(f"✅ Добавлен: {show['name']}")


@dp.message(Command("delete"))
async def delete(m: types.Message):
    query = m.text.replace("/delete", "").strip()

    if not query:
        await m.answer("Напиши: /delete Название")
        return

    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
        DELETE FROM series
        WHERE user_id=? AND name LIKE ?
        """, (m.from_user.id, f"%{query}%"))
        conn.commit()

    await m.answer("🗑 Удалено")


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


async def api_series_detail(request):
    series_id = request.match_info["id"]

    with db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT episodes_json FROM series WHERE id=?", (series_id,))
        row = cur.fetchone()

        if not row:
            return web.json_response({})

        episodes = json.loads(row[0])

        cur.execute("SELECT season, episode FROM watched WHERE series_id=?", (series_id,))
        watched = cur.fetchall()

    watched_set = {(w[0], w[1]) for w in watched}

    return web.json_response({
        "seasons": episodes,
        "watched": list(watched_set)
    })


async def api_toggle_watch(request):
    data = await request.json()

    series_id = data["series_id"]
    season = data["season"]
    episode = data["episode"]

    with db() as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT 1 FROM watched
        WHERE series_id=? AND season=? AND episode=?
        """, (series_id, season, episode))

        if cur.fetchone():
            cur.execute("""
            DELETE FROM watched
            WHERE series_id=? AND season=? AND episode=?
            """, (series_id, season, episode))
        else:
            cur.execute("""
            INSERT OR IGNORE INTO watched(series_id, season, episode)
            VALUES (?, ?, ?)
            """, (series_id, season, episode))

        conn.commit()

    return web.json_response({"ok": True})


# ================= WEB =================

async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series/{id}", api_series_detail)
    app.router.add_post("/api/toggle", api_toggle_watch)

    app.router.add_static("/static/", path="./web", name="static")

    async def index(request):
        return web.FileResponse("./web/index.html")

    app.router.add_get("/", index)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    print("🌐 WebApp работает")


# ================= MAIN =================

async def main():
    init_db()
    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )


if __name__ == "__main__":
    asyncio.run(main())
