import os
import asyncio
import json
import datetime
import aiohttp
import asyncpg

from aiohttp import web
from aiogram import Bot, Dispatcher, types

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL missing")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db_pool = None

# =========================
# DB INIT
# =========================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            name TEXT,
            poster TEXT
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            series_id INT,
            season INT,
            episode INT,
            air_date DATE
        );

        CREATE TABLE IF NOT EXISTS watched (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            series_id INT,
            season INT,
            episode INT
        );
        """)

# =========================
# TMDB
# =========================
async def fetch_tmdb_series(name):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={name}&language=ru-RU"
        async with session.get(url) as resp:
            data = await resp.json()
            if not data["results"]:
                return None
            return data["results"][0]

async def fetch_full_episodes(tmdb_id):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}&language=ru-RU"
        async with session.get(url) as resp:
            data = await resp.json()

        seasons = data.get("seasons", [])
        result = {}

        for s in seasons:
            sn = s["season_number"]
            if sn == 0:
                continue

            url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{sn}?api_key={TMDB_API_KEY}&language=ru-RU"
            async with session.get(url) as resp:
                s_data = await resp.json()

            eps = []
            for ep in s_data.get("episodes", []):
                eps.append({
                    "episode": ep["episode_number"],
                    "air_date": ep.get("air_date")
                })

            result[str(sn)] = eps

        return result

# =========================
# SAVE EPISODES
# =========================
async def save_episodes(conn, series_id, episodes_data, user_id):
    today = datetime.date.today()

    for season, eps in episodes_data.items():
        season = int(season)

        for ep in eps:
            ep_num = ep["episode"]
            air_date = ep["air_date"]

            await conn.execute("""
                INSERT INTO episodes (series_id, season, episode, air_date)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT DO NOTHING
            """, series_id, season, ep_num, air_date)

            # Netflix логика
            if air_date:
                air = datetime.datetime.strptime(air_date, "%Y-%m-%d").date()
                if air < today:
                    await conn.execute("""
                        INSERT INTO watched (user_id, series_id, season, episode)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT DO NOTHING
                    """, user_id, series_id, season, ep_num)

# =========================
# ADD SERIES
# =========================
async def add_series(name, user_id):
    tmdb = await fetch_tmdb_series(name)
    if not tmdb:
        return None

    tmdb_id = tmdb["id"]
    poster = f"https://image.tmdb.org/t/p/w500{tmdb['poster_path']}"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO series (name, poster)
            VALUES ($1,$2)
            RETURNING id
        """, name, poster)

        series_id = row["id"]

        episodes = await fetch_full_episodes(tmdb_id)
        await save_episodes(conn, series_id, episodes, user_id)

    return series_id

# =========================
# API: LIST
# =========================
async def api_series(request):
    user_id = int(request.query.get("user_id", 0))

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM series")

        result = []

        for r in rows:
            sid = r["id"]

            total = await conn.fetchval("""
                SELECT COUNT(*) FROM episodes WHERE series_id=$1
            """, sid)

            watched = await conn.fetchval("""
                SELECT COUNT(*) FROM watched 
                WHERE series_id=$1 AND user_id=$2
            """, sid, user_id)

            seasons = await conn.fetch("""
                SELECT season,
                       COUNT(*) as total,
                       COUNT(w.episode) as watched
                FROM episodes e
                LEFT JOIN watched w
                ON e.series_id=w.series_id 
                AND e.season=w.season 
                AND e.episode=w.episode 
                AND w.user_id=$2
                WHERE e.series_id=$1
                GROUP BY season
                ORDER BY season
            """, sid, user_id)

            seasons_data = {
                str(s["season"]): {
                    "total": s["total"],
                    "watched": s["watched"]
                } for s in seasons
            }

            result.append({
                "id": sid,
                "name": r["name"],
                "poster": r["poster"],
                "total": total,
                "watched": watched,
                "seasons": seasons_data
            })

    return web.json_response(result)

# =========================
# API: DETAIL
# =========================
async def api_series_detail(request):
    series_id = int(request.query.get("series_id"))
    user_id = int(request.query.get("user_id"))

    async with db_pool.acquire() as conn:
        series = await conn.fetchrow("SELECT * FROM series WHERE id=$1", series_id)

        eps = await conn.fetch("""
            SELECT season, episode, air_date
            FROM episodes
            WHERE series_id=$1
            ORDER BY season, episode
        """, series_id)

        watched = await conn.fetch("""
            SELECT season, episode FROM watched
            WHERE series_id=$1 AND user_id=$2
        """, series_id, user_id)

        watched_set = {(w["season"], w["episode"]) for w in watched}

        seasons = {}
        for e in eps:
            s = str(e["season"])
            seasons.setdefault(s, []).append({
                "episode": e["episode"],
                "air_date": str(e["air_date"]),
                "watched": (e["season"], e["episode"]) in watched_set
            })

    return web.json_response({
        "id": series["id"],
        "name": series["name"],
        "poster": series["poster"],
        "episodes": seasons
    })

# =========================
# API: TOGGLE
# =========================
async def toggle_episode(request):
    data = await request.json()

    user_id = data["user_id"]
    series_id = data["series_id"]
    season = data["season"]
    episode = data["episode"]

    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow("""
            SELECT * FROM watched
            WHERE user_id=$1 AND series_id=$2 AND season=$3 AND episode=$4
        """, user_id, series_id, season, episode)

        if exists:
            await conn.execute("""
                DELETE FROM watched
                WHERE user_id=$1 AND series_id=$2 AND season=$3 AND episode=$4
            """, user_id, series_id, season, episode)
        else:
            await conn.execute("""
                INSERT INTO watched (user_id, series_id, season, episode)
                VALUES ($1,$2,$3,$4)
            """, user_id, series_id, season, episode)

    return web.json_response({"status": "ok"})

# =========================
# WEB
# =========================
async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series_detail", api_series_detail)
    app.router.add_post("/api/toggle_episode", toggle_episode)

    app.router.add_static("/static", "./static")
    app.router.add_get("/", lambda r: web.FileResponse("./static/index.html"))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

# =========================
# BOT
# =========================
@dp.message()
async def handle_message(msg: types.Message):
    name = msg.text
    sid = await add_series(name, msg.from_user.id)

    if sid:
        await msg.answer(f"✅ Добавлен: {name}")
    else:
        await msg.answer("❌ Не найден сериал")

# =========================
# MAIN
# =========================
async def main():
    await init_db()
    await asyncio.gather(
        start_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
