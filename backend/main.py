import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio, subprocess, tempfile
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from config import APP_PORT, APP_HOST, HI_BASE, HI_UA
from database import init_db, get_search_cache, set_search_cache, get_episode_cache, set_episode_cache, add_history, get_history, clear_history, get_setting, set_setting, get_browse_cache, set_browse_cache, get_slug_map, set_slug_map
from api import hianime as hi
from api import anilist as al
import httpx

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Tatap", version="1.0.0", lifespan=lifespan)

def ok(data):
    return {"success": True, "data": data}
def fail(msg):
    return JSONResponse({"success": False, "error": msg}, status_code=200)

@app.get("/api/health")
async def health():
    try:
        import curl_cffi.requests as creq
        r = creq.get(HI_BASE + "/", impersonate="chrome124", timeout=10)
        reachable = r.status_code < 500
    except Exception:
        reachable = False
    return ok({"hianime": HI_BASE, "reachable": reachable})

@app.get("/api/search")
async def search(q: str = Query(""), limit: int = 15):
    q = q.strip()
    if not q:
        return fail("missing q")
    try:
        hit = await get_search_cache(q.lower())
        if hit:
            return ok({"results": hit, "cached": True})
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: hi.hianime_search(q, limit))
        await set_search_cache(q.lower(), res)
        return ok({"results": res, "cached": False})
    except Exception as e:
        return fail(str(e))

@app.get("/api/filters")
async def filters():
    return ok(hi.FILTERS)

@app.get("/api/catalog")
async def catalog(page: int = Query(1, ge=1, le=100)):
    """Katalog umum: semua judul, default urut populer."""
    try:
        import json as _json
        key = f"catalog|page={page}"
        hit = await get_browse_cache(key)
        if hit:
            hit["cached"] = True
            return ok(hit)
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: hi.browse({}, page))
        await set_browse_cache(key, res)
        res["cached"] = False
        return ok(res)
    except Exception as e:
        return fail(str(e))

@app.get("/api/seasonal")
async def seasonal(which: str = Query("now", pattern="^(now|prev)$"),
                   page: int = Query(1, ge=1, le=1)):
    """Daftar anime musim saat ini (now) atau satu musim sebelumnya (prev),
    diambil dari AniList. Judul dicocokkan ke slug hianime via search.
    AniList pagination over-reports setelah page 1, jadi endpoint dikunci 1 halaman."""
    try:
        import datetime as _dt
        year_cur, name_cur = al.current_season()
        if which == "now":
            season_name, season_year = name_cur, year_cur
        else:
            season_year, season_name = al.prev_season(name_cur, year_cur)

        key = f"seasonal|{which}|page={page}"
        hit = await get_browse_cache(key)
        if hit:
            hit["cached"] = True
            hit["season"] = season_name
            hit["year"] = season_year
            return ok(hit)

        loop = asyncio.get_running_loop()
        page_data = await loop.run_in_executor(
            None, lambda: al.season_page(season_name, season_year, page, 25))

        items_out = []
        for m in page_data.get("media", []):
            title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or ""
            if not title:
                continue
            slug = await get_slug_map(title)
            if slug is None:
                try:
                    res = await loop.run_in_executor(None, lambda t=title: hi.hianime_search(t, 5))
                    picked = None
                    if res:
                        rn = _slug_norm_match(title)
                        for c in res:
                            if c.get("title", "").lower() == rn.lower():
                                picked = c; break
                        if not picked and res:
                            picked = res[0]
                        if picked:
                            await set_slug_map(title, picked["id"])
                            slug = picked["id"]
                except Exception:
                    slug = None
            cover = (m.get("coverImage") or {})
            items_out.append({
                "id": slug or "",
                "title": title,
                "poster": cover.get("large") or cover.get("medium") or "",
                "type": _format_to_type(m.get("format")),
                "eps": m.get("episodes") or 0,
                "duration": (str(m.get("duration") or "") + "m") if m.get("duration") else "",
                "score": (m.get("averageScore") or 0) / 10.0 if m.get("averageScore") else 0,
                "anilist_id": m.get("id"),
                "site": m.get("siteUrl") or "",
                "matched": bool(slug),
            })

        page_info = page_data.get("pageInfo") or {}
        result = {
            "season": season_name,
            "year": season_year,
            "which": which,
            "items": items_out,
            "page": 1,
            "total_pages": 1,
            "total_items": len(items_out),
            "has_next": False,
            "cached": False,
        }
        await set_browse_cache(key, result)
        return ok(result)
    except Exception as e:
        return fail(str(e))


def _format_to_type(f):
    return {"TV": "TV", "TV_SHORT": "TV", "MOVIE": "Movie", "OVA": "OVA",
            "ONA": "ONA", "SPECIAL": "Special", "MUSIC": "Music"}.get(f or "", "")


def _slug_norm_match(title):
    import re as _re
    s = (title or "").lower()
    s = _re.sub(r"[^\w\s]", " ", s)
    return _re.sub(r"\s+", " ", s).strip()

@app.get("/api/browse")
async def browse_ep(
    type: str = Query(""), status: str = Query(""), rating: str = Query(""),
    score: str = Query(""), season: str = Query(""), language: str = Query(""),
    sort: str = Query(""), genre: str = Query(""), keyword: str = Query(""),
    sy: str = Query(""), sm: str = Query(""), ey: str = Query(""), em: str = Query(""),
    page: int = Query(1, ge=1, le=100),
):
    """Filter bebas — semua parameter sesuai form filter."""
    try:
        import json as _json
        params = {k: v for k, v in
                  {"type": type, "status": status, "rating": rating, "score": score,
                   "season": season, "language": language, "sort": sort, "genre": genre,
                   "keyword": keyword, "sy": sy, "sm": sm, "ey": ey, "em": em}.items() if v}
        key = "browse|" + _json.dumps(params, sort_keys=True) + f"|page={page}"
        hit = await get_browse_cache(key)
        if hit:
            hit["cached"] = True
            return ok(hit)
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: hi.browse(params, page))
        await set_browse_cache(key, res)
        res["cached"] = False
        return ok(res)
    except Exception as e:
        return fail(str(e))

@app.get("/api/anime/{slug}/episodes")
async def episodes(slug: str):
    try:
        loop = asyncio.get_running_loop()
        eps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
        return ok({"slug": slug, "episodes": eps, "total": len(eps)})
    except Exception as e:
        return fail(str(e))

@app.get("/api/stream/resolve")
async def resolve(slug: str = Query(""), ep: int = Query(1), mode: str = Query("sub"), q: str = Query("best")):
    try:
        mode = "dub" if mode.lower() == "dub" else "sub"
        hit = await get_episode_cache(slug, ep, mode)
        if hit:
            picked = hi.select_quality(hit["variants"], q)
            hit["picked"] = picked
            hit["cached"] = True
            return ok(hit)
        loop = asyncio.get_running_loop()
        maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
        got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode))
        await set_episode_cache(slug, ep, mode, got["master"], got["variants"], got.get("sub"), got.get("sub_lang"), got.get("referer"), got.get("server"))
        got["picked"] = hi.select_quality(got["variants"], q)
        got["cached"] = False
        return ok(got)
    except Exception as e:
        return fail(str(e))

@app.get("/api/player/video")
async def proxy_video(url: str = Query(""), referer: str = Query("")):
    # Proxy cepat: koneksi dipakai ulang, segmen di-stream (tanpa buffer penuh),
    # Range diteruskan supaya seek tidak unduh ulang dari awal.
    from fastapi import Request
    from fastapi.responses import StreamingResponse as _SR
    if not url.startswith("http"):
        return Response(status_code=400)
    from api.hianime import SEG_RE, SEG_KEY, SEG_IV, STRIP_BYTES, STRIP_RE
    import re as _re
    m = SEG_RE.search(url)
    if m:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            import base64 as _b64
            tok = m.group(1)
            s = tok.replace("-", "+").replace("_", "/")
            s += "=" * (-len(s) % 4)
            raw = _b64.b64decode(s)
            d = Cipher(algorithms.AES(SEG_KEY), modes.CBC(SEG_IV)).decryptor()
            pt = d.update(raw) + d.finalize()
            real = pt.decode("utf-8", errors="strict").strip().strip("\x00").strip()
            url = real if real.startswith("http") else url
        except Exception:
            pass
    return _SR(_pipe_video(url, referer), media_type="application/octet-stream",
               headers={"Access-Control-Allow-Origin": "*"})


_shared_client = None

def _client():
    global _shared_client
    if _shared_client is None:
        import httpx as _hx
        limits = _hx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=60.0)
        # Direct utama (tanpa proxy) — warp full-tunnel mesin tetap membungkus bila aktif.
        # Failover eksplisit per-request tidak didukung httpx shared; direct cukup
        # karena warp-cli full-tunnel sudah jadi jaring pengaman di level OS.
        _shared_client = _hx.AsyncClient(follow_redirects=True, timeout=_hx.Timeout(20.0, connect=8.0),
                                         limits=limits, http2=False)
    return _shared_client


async def _pipe_video(url: str, referer: str):
    import urllib.parse as _up
    from api.hianime import STRIP_BYTES as _SB, STRIP_RE as _SR2
    c = _client()
    try:
        async with c.stream("GET", url,
                            headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}) as r:
            ctype = r.headers.get("content-type", "")
            # playlist kecil: baca penuh + tulis ulang agar segmen tetap lewat proxy
            if "mpegurl" in ctype or url.endswith(".m3u8"):
                body = await r.aread()
                try:
                    txt = body.decode("utf-8", errors="strict")
                except Exception:
                    yield body
                    return
                if "#EXTM3U" not in txt:
                    yield body
                    return
                base = url.rsplit("/", 1)[0] + "/"
                out = []
                for ln in txt.splitlines():
                    s = ln.strip()
                    if not s or s.startswith("#"):
                        out.append(ln)
                        continue
                    absu = s if s.startswith("http") else _up.urljoin(base, s)
                    out.append(f"/api/player/video?url={_up.quote(absu, safe='')}&referer={_up.quote(referer or '', safe='')}")
                yield "\n".join(out).encode()
                return
            # segmen: teruskan per bongkah, buang prefix bila perlu
            skipped = 0
            need_strip = bool(_SR2.search(url))
            async for chunk in r.aiter_bytes(65536):
                if need_strip and skipped < _SB:
                    cut = min(len(chunk), _SB - skipped)
                    skipped += cut
                    chunk = chunk[cut:]
                    if not chunk:
                        continue
                if chunk:
                    yield chunk
    except Exception:
        return

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/api/player/sub")
async def proxy_sub(url: str = Query(""), referer: str = Query("")):
    if not url.startswith("http"):
        return Response(status_code=400)
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as c:
        r = await c.get(url, headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})})
        return Response(content=r.text, media_type="text/vtt")

@app.post("/api/play-mpv")
async def play_mpv(body: dict = None):
    body = body or {}
    slug, ep, mode = body.get("slug", ""), int(body.get("ep", 1)), body.get("mode", "sub")
    quality = body.get("quality", await get_setting("quality", "best"))
    try:
        loop = asyncio.get_running_loop()
        hit = await get_episode_cache(slug, ep, mode)
        if hit:
            got = dict(hit)
        else:
            maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
            got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode))
        picked = hi.select_quality(got["variants"], quality)
        cmd = ["mpv", f"--referer={got.get('referer','')}", picked["url"]]
        if got.get("sub"):
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    sr = await c.get(got["sub"], headers={"User-Agent": HI_UA, "Referer": got.get("referer","")})
                    fp = os.path.join(tempfile.gettempdir(), f"{slug}-ep{ep}.vtt")
                    open(fp, "w").write(sr.text)
                    cmd.insert(2, f"--sub-file={fp}")
            except Exception:
                pass
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await add_history(slug, body.get("title", slug), ep, mode)
        return ok({"cmd": cmd, "picked": picked})
    except FileNotFoundError:
        return fail("mpv tidak ditemukan. Install: sudo apt install mpv")
    except Exception as e:
        return fail(str(e))

@app.get("/api/history")
async def history():
    return ok(await get_history())

@app.post("/api/history")
async def save_hist(body: dict = None):
    body = body or {}
    await add_history(body.get("slug",""), body.get("title",""), int(body.get("episode",1)), body.get("mode","sub"))
    return ok(True)

@app.delete("/api/history")
async def del_hist():
    await clear_history()
    return ok(True)

@app.get("/api/settings")
async def get_set():
    return ok({"quality": await get_setting("quality","best"), "mode": await get_setting("mode","sub"), "player": await get_setting("player","browser")})

@app.post("/api/settings")
async def set_set(body: dict = None):
    body = body or {}
    for k in ("quality","mode","player"):
        if k in body:
            await set_setting(k, body[k])
    return await get_set()

app.mount("/js", StaticFiles(directory=os.path.join(frontend_dir, "js")), name="js")
app.mount("/css", StaticFiles(directory=os.path.join(frontend_dir, "css")), name="css")

@app.get("/")
async def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT, loop="asyncio", http="h11")
