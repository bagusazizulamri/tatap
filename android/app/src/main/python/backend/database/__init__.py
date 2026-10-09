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
        # Migrasi ringan: tambah kolom 'subtitles' (TEXT JSON array) untuk multi-track.
        # Gunakan pragma_table_info agar idempotent — kalau kolom sudah ada, skip.
        # Tidak ANDa ALTER TABLE di try/except supaya DB lama ter-upgrade otomatis.
        try:
            await db.execute("ALTER TABLE episode_cache ADD COLUMN subtitles TEXT DEFAULT '[]'")
        except Exception:
            # Duplicate column name → kolom sudah ada, aman di-skip.
            pass
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
        # Cache translated VTT — key: hash(src_url+referer+lang). TTL 30 hari.
        await db.execute("""CREATE TABLE IF NOT EXISTS subtitle_cache(
            key TEXT PRIMARY KEY, payload TEXT, fetched_at INTEGER)""")
        # Quota counter MyMemory per-day (Tier 2). Soft limit 4500/5000 char/day per-IP.
        await db.execute("""CREATE TABLE IF NOT EXISTS mychar_counts(
            day TEXT PRIMARY KEY, total INTEGER DEFAULT 0)""")
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
            # Multi-subtitle: parse kolom 'subtitles' (TEXT JSON array).
            # Fallback: kalau DB lama belum punya kolom (atau nil), dan 'sub' ada,
            # buat list 1-element dari 'sub' + 'sub_lang' agar client tetap punya
            # track untuk dropdown (kompatibel mundur dengan cache lama).
            try:
                d["subtitles"] = json.loads(d.get("subtitles") or "[]")
                if not isinstance(d["subtitles"], list):
                    d["subtitles"] = []
            except Exception:
                d["subtitles"] = []
            if not d["subtitles"] and d.get("sub"):
                d["subtitles"] = [{
                    "label": d.get("sub_lang") or "English",
                    "lang": "",
                    "url": d["sub"],
                    "default": True,
                }]
            return d

async def set_episode_cache(slug, ep, mode, master, variants, sub, sub_lang, referer, server,
                          subtitles=None):
    """Simpan cache episode. subtitles=list[{label,lang,url,default}], default []."""
    subs_json = json.dumps(subtitles or [])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT OR REPLACE INTO episode_cache
            (slug,ep,mode,master,variants,sub,sub_lang,referer,server,subtitles,fetched_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, ep, mode, master, json.dumps(variants), sub or "", sub_lang or "",
             referer or "", server or "", subs_json, _now()))
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


async def get_subtitle_cache(key, ttl=30 * 24 * 3600):
    """Return cached translated VTT TEXT atau None. TTL 30 hari."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT payload, fetched_at FROM subtitle_cache WHERE key=?",
                              (key,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            if _now() - row[1] > ttl:
                return None
            return row[0]


async def set_subtitle_cache(key, payload):
    """Cache translated VTT TEXT."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO subtitle_cache(key,payload,fetched_at) VALUES(?,?,?)",
            (key, payload, _now()),
        )
        await db.commit()


async def get_today_char_count(day):
    """Return MyMemory char count for today (UTC day string). 0 jika row missing."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT total FROM mychar_counts WHERE day=?", (day,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_today_char_count(day, n):
    """Atomically add n to today's count. Return new total."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mychar_counts(day,total) VALUES(?,?) "
            "ON CONFLICT(day) DO UPDATE SET total=total+?",
            (day, n, n),
        )
        await db.commit()
        async with db.execute("SELECT total FROM mychar_counts WHERE day=?", (day,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else n
