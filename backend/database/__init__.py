import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aiosqlite
import time
import json
from config import DATABASE_PATH

DB_PATH = DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("""CREATE TABLE IF NOT EXISTS search_cache(
            query TEXT PRIMARY KEY, payload TEXT, fetched_at INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS episode_cache(
            slug TEXT, ep INTEGER, mode TEXT, master TEXT, variants TEXT,
            sub TEXT, sub_lang TEXT, referer TEXT, server TEXT, fetched_at INTEGER,
            PRIMARY KEY(slug, ep, mode))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS watch_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, title TEXT,
            episode INTEGER, mode TEXT DEFAULT 'sub', progress INTEGER DEFAULT 0,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS browse_cache(
            key TEXT PRIMARY KEY, payload TEXT, fetched_at INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS slug_map(
            title TEXT PRIMARY KEY, slug TEXT, fetched_at INTEGER)""")
        await db.commit()

def _now():
    return int(time.time())

async def get_search_cache(query: str, ttl=86400):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT payload, fetched_at FROM search_cache WHERE query=?", (query,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            if _now() - row["fetched_at"] > ttl:
                return None
            try:
                return json.loads(row["payload"])
            except Exception:
                return None

async def set_search_cache(query: str, payload):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO search_cache(query,payload,fetched_at) VALUES(?,?,?)",
                         (query, json.dumps(payload), _now()))
        await db.commit()

async def get_episode_cache(slug: str, ep: int, mode: str, ttl=12*3600):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM episode_cache WHERE slug=? AND ep=? AND mode=?",
                              (slug, ep, mode)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            if _now() - d["fetched_at"] > ttl:
                return None
            try:
                d["variants"] = json.loads(d["variants"] or "[]")
            except Exception:
                d["variants"] = []
            return d

async def set_episode_cache(slug, ep, mode, master, variants, sub, sub_lang, referer, server):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT OR REPLACE INTO episode_cache
            (slug,ep,mode,master,variants,sub,sub_lang,referer,server,fetched_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (slug, ep, mode, master, json.dumps(variants), sub or "", sub_lang or "",
             referer or "", server or "", _now()))
        await db.commit()

async def add_history(slug, title, episode, mode="sub", progress=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO watch_history(slug,title,episode,mode,progress) VALUES(?,?,?,?,?)",
                         (slug, title, episode, mode, progress))
        await db.commit()

async def get_history(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM watch_history ORDER BY played_at DESC LIMIT ?", (limit,)) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def clear_history():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM watch_history")
        await db.commit()

async def get_browse_cache(key: str, ttl=6*3600):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT payload, fetched_at FROM browse_cache WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            if _now() - row["fetched_at"] > ttl:
                return None
            try:
                return json.loads(row["payload"])
            except Exception:
                return None

async def set_browse_cache(key: str, payload):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO browse_cache(key,payload,fetched_at) VALUES(?,?,?)",
                         (key, json.dumps(payload), _now()))
        await db.commit()

async def get_setting(key, default=""):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
        await db.commit()


def _slug_norm(title):
    import re as _re
    s = (title or "").lower()
    s = _re.sub(r"[^\w\s]", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


async def get_slug_map(title, ttl=7*24*3600):
    key = _slug_norm(title)
    if not key:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT slug, fetched_at FROM slug_map WHERE title=?", (key,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            if _now() - row["fetched_at"] > ttl:
                return None
            return row["slug"]


async def set_slug_map(title, slug):
    key = _slug_norm(title)
    if not key or not slug:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO slug_map(title,slug,fetched_at) VALUES(?,?,?)",
                         (key, slug, _now()))
        await db.commit()
