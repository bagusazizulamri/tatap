import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio, subprocess, tempfile
from fastapi import FastAPI, Query, HTTPException
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

@app.get("/api/ping")
async def ping():
    return ok({"status": "running"})

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

@app.get("/api/genres")
async def genres():
    """Daftar genre dari hianime /browse sidebar. Cache 24 jam."""
    try:
        key = "genres|list"
        hit = await get_browse_cache(key, ttl=24*3600)
        if hit:
            return ok({"list": hit["list"], "cached": True})
        loop = asyncio.get_running_loop()
        out = await loop.run_in_executor(None, hi.scrape_genres)
        await set_browse_cache(key, {"list": out})
        return ok({"list": out, "cached": False})
    except Exception as e:
        return fail(str(e))

@app.get("/api/seasonal")
async def seasonal(which: str = Query("", pattern="^(now|prev)$|^$"),
                   season: str = Query("", pattern="^(winter|spring|summer|fall)$|^$"),
                   year: int = Query(0, ge=0, le=2100),
                   page: int = Query(1, ge=1, le=1)):
    """Daftar anime per musim (AniList).
    which=now|prev = musim saat ini / sebelumnya.
    season+year = musim spesifik (contoh: season=fall year=2024).
    AniList pagination over-reports setelah page 1, jadi endpoint dikunci 1 halaman."""
    try:
        if season and year >= 1900:
            season_name = season
            season_year = year
            cache_id = f"{season}_{year}"
        else:
            year_cur, name_cur = al.current_season()
            if which == "now":
                season_name, season_year = name_cur, year_cur
            elif which == "prev":
                season_year, season_name = al.prev_season(name_cur, year_cur)
            else:
                return fail("butuh which=now|prev atau season=<nama>&year=<tahun>")
            cache_id = which

        key = f"seasonal|{cache_id}|page={page}"
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
    """Normalisasi judul untuk perbandingan dengan hasil hianime_search.
    Import dari database agar konsisten dengan key yang dipakai slug_map."""
    from database import _slug_norm
    return _slug_norm(title)


@app.get("/api/upcoming-episodes")
async def upcoming_episodes(days: int = Query(7, ge=1, le=30)):
    """Episode yang rilis dalam N hari ke depan (default 7), dari Page.airingSchedules.
    Filter musim akurat: hanya anime yang season-nya cocok dengan bulan rilis (atau
    masih ongoing = season=null). Lalu matched ke hianime. Cache 1 jam."""
    try:
        import datetime as _dt
        now = int(_dt.datetime.utcnow().timestamp())
        # Tentukan season release-window yang relevan.
        cur_year, cur_season = al.current_season()
        order = ["winter", "spring", "summer", "fall"]
        idx = order.index(cur_season)
        prev_season = order[(idx - 1) % 4]
        prev_year = cur_year if idx > 0 else cur_year - 1
        end = now + days * 86400
        key = f"upcoming|days={days}"
        hit = await get_browse_cache(key, ttl=3600)
        if hit:
            hit["cached"] = True
            return ok(hit)

        loop = asyncio.get_running_loop()
        # perPage 100 — AniList 50-100 item 7 hari tetap manageable (max 4 req / hari
        # dari cache 1 jam, ~16 episode/matched). Filter musim di Python.
        schedules = await loop.run_in_executor(None, lambda: al.anilist_schedules(now, end, 100))

        items_out = []
        seen = set()
        cur_season_up = cur_season.upper()
        prev_season_up = prev_season.upper()
        for s in schedules:
            m = s.get("media") or {}
            sy = m.get("seasonYear")
            se = m.get("season")
            if se is not None:
                if sy != cur_year and sy != prev_year:
                    continue
                if se not in (cur_season_up, prev_season_up):
                    continue
            mid = m.get("id")
            if mid in seen:
                continue
            seen.add(mid)
            title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or ""
            if not title:
                continue
            slug = await get_slug_map(title)
            if not slug:
                try:
                    res = await loop.run_in_executor(None, lambda t=title: hi.hianime_search(t, 5))
                    if res:
                        rn = _slug_norm_match(title)
                        picked = None
                        for c in res:
                            if c.get("title", "").lower() == rn.lower():
                                picked = c; break
                        if not picked:
                            picked = res[0]
                        await set_slug_map(title, picked["id"])
                        slug = picked["id"]
                except Exception:
                    slug = None
            if not slug:
                continue

            airing_dt = _dt.datetime.fromtimestamp(s["airingAt"])
            cover = (m.get("coverImage") or {})
            items_out.append({
                "id": slug,
                "title": title,
                "anilist_id": m.get("id"),
                "poster": cover.get("large") or cover.get("medium") or "",
                "episode": s.get("episode"),
                "airing_at": int(s["airingAt"]),
                "airing_at_iso": airing_dt.isoformat() + "Z",
                "weekday": airing_dt.strftime("%a"),
                "date": airing_dt.strftime("%d %b"),
                "time": airing_dt.strftime("%H:%M"),
                "matched": True,
            })

        result = {
            "items": items_out,
            "days": days,
            "total": len(items_out),
            "current_season": cur_season,
            "previous_season": prev_season,
            "current_year": cur_year,
            "cached": False,
        }
        await set_browse_cache(key, result)
        return ok(result)
    except Exception as e:
        return fail(str(e))

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
            # Pastikan 'subtitles' selalu list (bukan None) di response — UI
            # bisa render dropdown tanpa null-check tambahan.
            hit["subtitles"] = hit.get("subtitles") or []
            return ok(hit)
        loop = asyncio.get_running_loop()
        maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
        got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode))
        # Simpan subtitle list (default []) ke cache agar subsequent request langsung baca.
        await set_episode_cache(slug, ep, mode, got["master"], got["variants"],
                                got.get("sub"), got.get("sub_lang"),
                                got.get("referer"), got.get("server"),
                                subtitles=got.get("subtitles") or [])
        got["picked"] = hi.select_quality(got["variants"], q)
        got["cached"] = False
        got["subtitles"] = got.get("subtitles") or []
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
    # Catatan: dramahot.top dulu diblokir karena TLS-RST dari region kita.
    # Per Oct 2026 host sudah bisa dijangkau (TLS handshake sukses) sehingga
    # blokir di-hapus; kalau mati lagi, _mark_dead() di hianime.py akan masukkan
    # ke negative cache dan smart-fallback skip server ZokoAnime secara otomatis.
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
    # Probe status cepat sebelum StreamingResponse — kalau 4xx/5xx, return
    # langsung 502 agar HLS.js deteksi fragLoadError. (StreamingResponse swallows
    # HTTPException dari dalam generator, jadi probe wajib sebelum spawn _SR.)
    try:
        c = _client()
        async with c.stream("GET", url,
                            headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}) as r:
            if r.status_code >= 400:
                # Drain sebelum close agar connection kembali ke pool.
                try:
                    await r.aread()
                except Exception:
                    pass
                return Response(status_code=502,
                                content=f"upstream {r.status_code}".encode(),
                                media_type="text/plain")
    except HTTPException as e:
        return Response(status_code=e.status_code, content=str(e.detail).encode(),
                        media_type="text/plain")
    except Exception as e:
        return Response(status_code=502,
                        content=f"upstream error: {type(e).__name__}".encode(),
                        media_type="text/plain")
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
    # Catatan: dramahot.top dulu diblokir karena TLS-RST dari region kita.
    # Per Oct 2026 host sudah bisa dijangkau (TLS handshake sukses) sehingga
    # blokir di-hapus; kalau mati lagi, _mark_dead() di hianime.py akan masukkan
    # ke negative cache dan smart-fallback skip server ZokoAnime secara otomatis.
    c = _client()
    upstream_status = None
    try:
        async with c.stream("GET", url,
                            headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}) as r:
            upstream_status = r.status_code
            ctype = r.headers.get("content-type", "")
            if upstream_status >= 400:
                raise HTTPException(status_code=502, detail=f"upstream {upstream_status}")
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
    except HTTPException:
        raise
    except Exception as e:
        # Upstream error (RST, timeout, DNS) — surface ke client sebagai 502
        # agar HLS.js deteksi networkError, bukan hang di buffering.
        raise HTTPException(status_code=502, detail=f"upstream error: {type(e).__name__}")

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

def find_mpv_binary():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root_dir, "bin", "mpv.exe"),
        os.path.join(root_dir, "bin", "mpv"),
        os.path.join(root_dir, "mpv", "mpv.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    import shutil
    return shutil.which("mpv.exe" if sys.platform == "win32" else "mpv")

@app.post("/api/play-mpv")
async def play_mpv(body: dict = None):
    body = body or {}
    slug, ep, mode = body.get("slug", ""), int(body.get("ep", 1)), body.get("mode", "sub")
    quality = body.get("quality", await get_setting("quality", "best"))
    # Opsional: user pilih subtitle spesifik via UI ("sub_url" berisi URL track
    # yang aktif). Backend tetap attach seluruh subtitles[] ke MPV (--sub-file
    # bisa lebih dari satu) supaya user bisa cycle lewat tombol 'j'.
    preferred_sub_url = body.get("sub_url") or ""
    try:
        mpv_bin = find_mpv_binary()
        if not mpv_bin:
            return fail("mpv tidak ditemukan. Taruh mpv.exe di folder 'bin/' atau install mpv ke sistem.")

        loop = asyncio.get_running_loop()
        hit = await get_episode_cache(slug, ep, mode)
        if hit:
            got = dict(hit)
        else:
            maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
            got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode, slug))
        picked = hi.select_quality(got["variants"], quality)
        cmd = [mpv_bin, f"--referer={got.get('referer','')}", picked["url"]]
        # Kumpulkan subtitle files. Prioritas:
        #   1) preferred_sub_url (kalau client pilih spesifik), atau default 'sub'
        #   2) SELURUH subtitles[] dari cache/result, agar semua track terpasang
        #      dan user bisa cycle via 'j' di MPV.
        # File VTT didownload ke tempdir (mpv butuh path lokal). File yang gagal
        # didownload di-skip agar tidak menggagalkan playback.
        # Catatan: subs_all mengandung tracks unik saja — kalau 'sub' (default)
        # sudah ada di subtitles[] dengan URL sama, skip supaya tidak duplikat.
        subs_all = []
        seen_urls = set()
        for s in (got.get("subtitles") or []):
            url = (s or {}).get("url")
            if url and url not in seen_urls:
                subs_all.append(s)
                seen_urls.add(url)
        if preferred_sub_url and preferred_sub_url not in seen_urls:
            subs_all.append({"label": "Selected", "url": preferred_sub_url,
                             "lang": "", "default": False})
            seen_urls.add(preferred_sub_url)
        elif got.get("sub") and got["sub"] not in seen_urls:
            # Pakai default 'sub' hanya kalau belum ada di subtitles[].
            subs_all.append({"label": got.get("sub_lang") or "Default",
                             "url": got["sub"], "lang": "", "default": True})
            seen_urls.add(got["sub"])

        # Helper download async; return None kalau gagal (skip track).
        async def _download_sub(url):
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    sr = await c.get(url, headers={"User-Agent": HI_UA,
                                                    "Referer": got.get("referer", "")})
                    if sr.status_code != 200 or not sr.text:
                        return None
                    fp = os.path.join(tempfile.gettempdir(),
                                      f"{slug}-ep{ep}-{abs(hash(url)) % 10**8}.vtt")
                    open(fp, "w").write(sr.text)
                    return fp
            except Exception:
                return None

        downloaded = []
        for s in subs_all:
            url = (s or {}).get("url")
            if not url:
                continue
            fp = await _download_sub(url)
            if fp:
                downloaded.append(fp)

        # Masukkan --sub-file sebelum URL. mpv izinkan multiple --sub-file.
        # Sisip di posisi 2 (setelah mpv_bin + --referer=) agar tidak geser posisi URL.
        for fp in downloaded:
            cmd.insert(2, f"--sub-file={fp}")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        await add_history(slug, body.get("title", slug), ep, mode)
        return ok({"cmd": cmd, "picked": picked, "subs_attached": len(downloaded)})
    except Exception as e:
        return fail(str(e))

@app.post("/api/shutdown")
async def shutdown():
    def _do_exit():
        import time
        time.sleep(0.3)
        os._exit(0)
    import threading
    threading.Thread(target=_do_exit, daemon=True).start()
    return ok({"message": "Server shutting down..."})

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
    return ok({
        "quality": await get_setting("quality", "best"),
        "mode": await get_setting("mode", "sub"),
        "player": await get_setting("player", "browser"),
        # Preferensi bahasa subtitle user. Default "English" karena sebagian besar
        # sumber (Megaplay, ZokoAnime) punya English sebagai track default. Kalau
        # user pernah pilih bahasa lain, disimpan di sini dan dipakai frontend
        # untuk auto-select track di episode berikutnya.
        "sub_lang": await get_setting("sub_lang", "English"),
    })

@app.post("/api/settings")
async def set_set(body: dict = None):
    body = body or {}
    for k in ("quality", "mode", "player", "sub_lang"):
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
