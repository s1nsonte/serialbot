import os
import json
import asyncio
import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL missing")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db_pool = None


# =========================
# 🔌 DB INIT
# =========================
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
            episodes_json JSONB
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS watched (
            id SERIAL PRIMARY KEY,
            series_id INT,
            season INT,
            episode INT
        );
        """)


# =========================
# 📺 API: список сериалов
# =========================
async def api_series(request):
    user_id = request.query.get("user_id")

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM series WHERE user_id=$1",
            int(user_id)
        )

        result = []

        for r in rows:
            episodes = r["episodes_json"] or {}

            seasons = {}
            total = 0

            for season, eps in episodes.items():
                total_eps = len(eps)

                watched = await conn.fetchrow("""
                    SELECT COUNT(*) FROM watched 
                    WHERE series_id=$1 AND season=$2
                """, r["id"], int(season))

                watched_count = watched["count"]

                seasons[season] = {
                    "watched": watched_count,
                    "total": total_eps
                }

                total += total_eps

            watched_total = await conn.fetchrow("""
                SELECT COUNT(*) FROM watched 
                WHERE series_id=$1
            """, r["id"])

            result.append({
                "id": r["id"],
                "name": r["name"],
                "poster": r["poster"],
                "watched": watched_total["count"],
                "total": total,
                "seasons": seasons
            })

        return web.json_response(result)


# =========================
# 🎬 API: детали сериала
# =========================
async def api_series_detail(request):
    series_id = request.query.get("series_id")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM series WHERE id=$1",
            int(series_id)
        )

        watched = await conn.fetch("""
            SELECT season, episode FROM watched 
            WHERE series_id=$1
        """, int(series_id))

        return web.json_response({
            "id": row["id"],
            "name": row["name"],
            "poster": row["poster"],
            "episodes": row["episodes_json"],
            "watched": [[w["season"], w["episode"]] for w in watched]
        })


# =========================
# 🔄 API: toggle эпизода
# =========================
async def api_toggle_episode(request):
    data = await request.json()

    series_id = data["series_id"]
    season = data["season"]
    episode = data["episode"]

    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow("""
            SELECT * FROM watched 
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


# =========================
# ➕ API: добавить сериал (ТЕСТ)
# =========================
async def api_add_series(request):
    data = await request.json()

    user_id = data["user_id"]
    name = data["name"]
    poster = data["poster"]

    # пример эпизодов (заглушка)
    episodes = {
        "1": [{"episode": i, "air_date": "2024-01-01"} for i in range(1, 17)],
        "2": [{"episode": i, "air_date": "2024-02-01"} for i in range(1, 17)]
    }

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO series (user_id, name, poster, episodes_json)
            VALUES ($1, $2, $3, $4)
        """, user_id, name, poster, json.dumps(episodes))

    return web.json_response({"ok": True})


# =========================
# 🚀 WEB SERVER
# =========================
async def start_web():
    app = web.Application()

    app.router.add_get("/api/series", api_series)
    app.router.add_get("/api/series_detail", api_series_detail)
    app.router.add_post("/api/toggle_episode", api_toggle_episode)
    app.router.add_post("/api/add_series", api_add_series)

    return app


# =========================
# ▶️ MAIN
# =========================
async def main():
    await init_db()

    app = await start_web()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
