import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio, subprocess, tempfile
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from config import APP_PORT, APP_HOST, HI_BASE, HI_UA
from database import init_db, get_search_cache, set_search_cache, get_episode_cache, set_episode_cache, add_history, get_history, clear_history, get_setting, set_setting, get_browse_cache, set_browse_cache, get_slug_map, set_slug_map, get_subtitle_cache, set_subtitle_cache, get_today_char_count, add_today_char_count
from api import hianime as hi
from api import anilist as al
from api import otakudesu as otaku
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

        # Kumpulkan judul dulu, lalu batch-match slug paralel.
        media_list = page_data.get("media") or []
        titles = []
        media_by_title = {}
        for m in media_list:
            title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or ""
            if not title:
                continue
            titles.append(title)
            media_by_title[title] = m
        slug_pairs = await _match_slugs_batch(titles)
        slug_by_title = {t: s for t, s in slug_pairs}

        items_out = []
        for title, m in media_by_title.items():
            slug = slug_by_title.get(title)
            if not slug:
                continue
            cover = (m.get("coverImage") or {})
            items_out.append({
                "id": slug,
                "title": title,
                "poster": cover.get("large") or cover.get("medium") or "",
                "type": _format_to_type(m.get("format")),
                "eps": m.get("episodes") or 0,
                "duration": (str(m.get("duration") or "") + "m") if m.get("duration") else "",
                "score": (m.get("averageScore") or 0) / 10.0 if m.get("averageScore") else 0,
                "anilist_id": m.get("id"),
                "site": m.get("siteUrl") or "",
                "matched": True,
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


async def _match_slug_one(loop, title):
    """Resolve 1 judul -> slug hianime via cache get/set. Return None jika gagal."""
    slug = await get_slug_map(title)
    if slug:
        return slug
    try:
        res = await loop.run_in_executor(None, lambda t=title: hi.hianime_search(t, 5))
        if res:
            rn = _slug_norm_match(title)
            picked = None
            for c in res:
                if c.get("title", "").lower() == rn.lower():
                    picked = c
                    break
            if not picked:
                picked = res[0]
            if picked:
                await set_slug_map(title, picked["id"])
                return picked["id"]
    except Exception:
        pass
    return None


# Batas request paralel ke hianime per scrape (mencegah rate-limit).
_SLUG_MATCH_CONCURRENCY = 8


async def _match_slugs_batch(titles):
    """Match banyak judul ke slug hianime secara paralel.
    Output: list of (title, slug_or_None) dengan urutan input dipertahankan."""
    titles = list(titles)
    if not titles:
        return []
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(_SLUG_MATCH_CONCURRENCY)
    async def one(t):
        async with sem:
            return t, await _match_slug_one(loop, t)
    pairs = await asyncio.gather(*(one(t) for t in titles))
    return pairs


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

        # Filter musim & kumpulkan judul yang lolos untuk match slug paralel.
        cur_season_up = cur_season.upper()
        prev_season_up = prev_season.upper()
        pending = []
        seen = set()
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
            pending.append((s, title))
        # Match paralel (lihat timeline & urutan paralel di _match_slugs_batch).
        slug_pairs = await _match_slugs_batch([t for _, t in pending])
        slug_by_title = {t: s for t, s in slug_pairs}

        items_out = []
        for s, title in pending:
            slug = slug_by_title.get(title)
            if not slug:
                continue

            airing_dt = _dt.datetime.fromtimestamp(s["airingAt"])
            cover = (s.get("media") or {}).get("coverImage", {})
            items_out.append({
                "id": slug,
                "title": title,
                "anilist_id": s.get("media", {}).get("id"),
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
async def resolve(slug: str = Query(""), ep: int = Query(1), mode: str = Query("sub"), q: str = Query("best"), source: str = Query("")):
    try:
        mode = "dub" if mode.lower() == "dub" else "sub"
        pref_source = (await get_setting("preferred_source", "hianime")).lower()
        active_source = (source or pref_source or "hianime").lower()

        # Cache key mencakup source agar stream tidak tertukar
        cache_slug = f"{active_source}:{slug}" if active_source != "hianime" else slug
        hit = await get_episode_cache(cache_slug, ep, mode)
        if hit:
            picked = hi.select_quality(hit["variants"], q)
            hit["picked"] = picked
            hit["cached"] = True
            hit["subtitles"] = hit.get("subtitles") or []
            hit["source"] = active_source
            return ok(hit)

        loop = asyncio.get_running_loop()
        got = None
        last_error = None

        if active_source == "otakudesu":
            try:
                got = await loop.run_in_executor(None, lambda: otaku.resolve_stream(slug, ep))
            except Exception as e:
                last_error = e
                # Fallback ke hianime kalau user pakai auto
                if source == "auto" or not source:
                    try:
                        maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
                        got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode, slug))
                        active_source = "hianime"
                        cache_slug = slug
                    except Exception:
                        pass
        else:
            try:
                maps = await loop.run_in_executor(None, lambda: hi.hianime_episodes(slug))
                got = await loop.run_in_executor(None, lambda: hi.hianime_m3u8(maps, ep, mode, slug))
            except Exception as e:
                last_error = e
                # Fallback ke otakudesu jika hianime gagal
                if source == "auto" or not source:
                    try:
                        got = await loop.run_in_executor(None, lambda: otaku.resolve_stream(slug, ep))
                        active_source = "otakudesu"
                        cache_slug = f"otakudesu:{slug}"
                    except Exception:
                        pass

        if not got:
            raise last_error or RuntimeError("Stream gagal di-resolve dari semua sumber")

        got["source"] = active_source
        got["picked"] = hi.select_quality(got["variants"], q)
        got["cached"] = False
        got["subtitles"] = got.get("subtitles") or []

        # Simpan cache episode
        await set_episode_cache(cache_slug, ep, mode, got["master"], got["variants"],
                                got.get("sub"), got.get("sub_lang"),
                                got.get("referer"), got.get("server"),
                                subtitles=got["subtitles"])
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
    # Jika host terdeteksi diblokir DPI ISP, gunakan TLS desync murni (aman dari Sangfor)
    from api.hianime import _host_from, _BLOCKED_DPI_HOSTS
    host = _host_from(url)
    if host in _BLOCKED_DPI_HOSTS:
        return _SR(_pipe_desync_video(url, referer), media_type="application/octet-stream",
                   headers={"Access-Control-Allow-Origin": "*"})

    try:
        c = _get_video_client(url)
        async with c.stream("GET", url,
                            headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}) as r:
            if r.status_code >= 400:
                return Response(status_code=502,
                                content=f"upstream {r.status_code}".encode(),
                                media_type="text/plain")
    except HTTPException as e:
        return Response(status_code=e.status_code, content=str(e.detail).encode(),
                        media_type="text/plain")
    except Exception as e:
        # Jika direct gagal karena blokir DPI ISP, tandai host dan gunakan TLS desync
        err_str = str(e).lower()
        if "reset" in err_str or "ssl" in err_str or "recv failure" in err_str:
            _BLOCKED_DPI_HOSTS.add(host)
            return _SR(_pipe_desync_video(url, referer), media_type="application/octet-stream",
                       headers={"Access-Control-Allow-Origin": "*"})
        return Response(status_code=502,
                        content=f"upstream error: {type(e).__name__}".encode(),
                        media_type="text/plain")
    return _SR(_pipe_video(url, referer), media_type="application/octet-stream",
               headers={"Access-Control-Allow-Origin": "*"})


async def _pipe_desync_video(url: str, referer: str):
    """Streaming video via TLS Client Hello Desynchronization (Direct TCP 443 tanpa VPN)."""
    import urllib.parse as _up
    from api.desync import tls_desync_request, tls_desync_stream
    import asyncio
    
    headers = {"Referer": referer} if referer else {}
    loop = asyncio.get_running_loop()
    
    # Playlist m3u8: baca penuh dan rewrite URL agar segmen tetap lewat proxy Tatap
    if ".m3u8" in url:
        body = await loop.run_in_executor(None, lambda: tls_desync_request(url, headers=headers))
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

    # Segmen TS: stream per bongkah via desync TLS generator
    async for chunk in tls_desync_stream(url, headers=headers):
        if chunk:
            yield chunk


_direct_client = None

def _get_video_client(url: str):
    """Direct client murni untuk video normal (Megaplay, Otakudesu, dll.)."""
    global _direct_client
    import httpx as _hx
    if _direct_client is None:
        limits = _hx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=60.0)
        _direct_client = _hx.AsyncClient(
            follow_redirects=True,
            timeout=_hx.Timeout(25.0, connect=8.0),
            limits=limits,
            http2=False
        )
    return _direct_client


async def _pipe_video(url: str, referer: str):
    import urllib.parse as _up
    from api.hianime import STRIP_BYTES as _SB, STRIP_RE as _SR2
    c = _get_video_client(url)
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
async def proxy_sub(url: str = Query(""),
                   referer: str = Query(""),
                   lang: str = Query("", pattern="^(en|id|ja|es|fr|de|pt|ko|zh)$|^$"),
                   src: str = Query("en", pattern="^(en|ja|es|fr|de|pt|ko|zh)$")):
    """Proxy subtitle VTT. Jika `lang` diisi dan berbeda dari source, jalankan
    multi-tier fallback translate (Tier 1 OpenAI API → Tier 2 MyMemory → Tier 3 source)."""
    if not url.startswith("http"):
        return Response(status_code=400)
    # Helper fetcher yang mendukung desync bila host terblokir DPI
    async def _fetch_sub_text(target_url, ref):
        from api.hianime import _host_from, _BLOCKED_DPI_HOSTS
        h = _host_from(target_url)
        if h in _BLOCKED_DPI_HOSTS:
            from api.desync import tls_desync_request
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, lambda: tls_desync_request(target_url, headers={"Referer": ref} if ref else {}))
            return raw.decode("utf-8", errors="replace")
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as c:
            r = await c.get(target_url, headers={"User-Agent": HI_UA,
                                                 **({"Referer": ref} if ref else {})})
            return r.text

    # Lang kosong → return source apa adanya.
    if not lang or lang == src:
        try:
            content = await _fetch_sub_text(url, referer)
            return Response(content=content, media_type="text/vtt")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"gagal mengambil subtitle: {e}")

    # Cache key: hash dari URL+referer+lang (deterministic).
    import hashlib
    cache_key = "sub|" + hashlib.sha1(
        (url + "|" + (referer or "") + "|" + lang).encode("utf-8")
    ).hexdigest()
    hit = await get_subtitle_cache(cache_key)
    if hit is not None:
        try:
            from api.translate import log_translate
            log_translate(f"Cache HIT subtitle [{lang}]: dimuat instan dari database lokal")
        except Exception:
            pass
        resp = Response(content=hit, media_type="text/vtt")
        resp.headers["X-Translate-Tier"] = "cached"
        return resp
    # Fetch source subtitle.
    try:
        text = await _fetch_sub_text(url, referer)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"gagal mengambil subtitle: {e}")
    # Multi-tier translate.
    try:
        from api.translate import parse_vtt, build_vtt, call_openai_translate, call_mymemory_translate
        cues = parse_vtt(text)
        if not cues:
            resp = Response(content=text, media_type="text/vtt")
            resp.headers["X-Translate-Tier"] = "source"
            resp.headers["X-Translate-Error"] = "Subtitle kosong atau format tidak didukung"
            return resp
        tier = await _translate_with_fallback(cues, src, lang)
        new_text = build_vtt(tier["cues"])
    except Exception as e:
        new_text = text
        tier = {"cues": None, "level": "source", "error": str(e)}
    # Cache hasil hanya jika berhasil diterjemahkan (tier1 / tier2).
    # Jangan cache jika jatuh ke source fallback agar user bisa retry saat set apikey.
    if tier.get("level") in ("tier1", "tier2"):
        await set_subtitle_cache(cache_key, new_text)
    resp = Response(content=new_text, media_type="text/vtt")
    resp.headers["X-Translate-Tier"] = tier.get("level", "source")
    if tier.get("error"):
        # Bersihkan newline dari header agar valid HTTP header
        clean_err = re.sub(r"[\r\n]+", " ", str(tier["error"])).strip()
        resp.headers["X-Translate-Error"] = clean_err[:200]
    return resp


async def _translate_with_fallback(cues, src, tgt):
    """Multi-tier translate:
    Tier 1: Google GTX Web RPC (Unmetered, Zero-Key, Super Cepat ~1-2s)
    Tier 2: MyMemory Public REST (Fallback cloud gratis)
    Tier 3: Source original fallback (Safety net, tanpa crash)
    Return {"cues": [...], "level": "tier1|tier2|source", "error": "..."}."""
    from api.translate import call_gtx_translate, call_mymemory_translate, estimate_chars
    import datetime as _dt
    last_err = ""

    # Tier 1: Google GTX Web RPC (Unmetered, Zero-Key)
    try:
        translated = await call_gtx_translate(cues, src, tgt)
        return {"cues": translated, "level": "tier1", "error": ""}
    except Exception as e:
        last_err = f"Tier 1 (Google GTX) error: {e}"
        print(f"[TRANSLATE TIER 1 ERROR] {e}")

    # Tier 2: MyMemory dengan soft-limit per-IP per-day.
    day = _dt.datetime.utcnow().strftime("%Y-%m-%d")
    used = await get_today_char_count(day)
    needed = estimate_chars(cues)
    SOFT_LIMIT = 4500
    if used + needed <= SOFT_LIMIT:
        try:
            translated = await call_mymemory_translate(cues, src, tgt)
            await add_today_char_count(day, needed)
            return {"cues": translated, "level": "tier2", "error": ""}
        except Exception as e:
            if not last_err:
                last_err = f"MyMemory error: {e}"
    else:
        if not last_err:
            last_err = f"Kuota gratis MyMemory harian habis ({used}/{SOFT_LIMIT} char)"

    # Tier 3: source fallback (return cues asli dengan label source).
    return {"cues": cues, "level": "source", "error": last_err}

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
                from api.hianime import _host_from, _BLOCKED_DPI_HOSTS
                h = _host_from(url)
                if h in _BLOCKED_DPI_HOSTS:
                    from api.desync import tls_desync_request
                    loop = asyncio.get_running_loop()
                    raw = await loop.run_in_executor(None, lambda: tls_desync_request(url, headers={"Referer": got.get("referer", "")}))
                    text = raw.decode("utf-8", errors="replace")
                else:
                    async with httpx.AsyncClient(timeout=15) as c:
                        sr = await c.get(url, headers={"User-Agent": HI_UA,
                                                        "Referer": got.get("referer", "")})
                        if sr.status_code != 200 or not sr.text:
                            return None
                        text = sr.text

                if not text:
                    return None
                fp = os.path.join(tempfile.gettempdir(),
                                  f"{slug}-ep{ep}-{abs(hash(url)) % 10**8}.vtt")
                open(fp, "w").write(text)
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
        "preferred_source": await get_setting("preferred_source", "hianime"),
        # Preferensi bahasa subtitle user. Default "English" karena sebagian besar
        # sumber (Megaplay, ZokoAnime) punya English sebagai track default. Kalau
        # user pernah pilih bahasa lain, disimpan di sini dan dipakai frontend
        # untuk auto-select track di episode berikutnya.
        "sub_lang": await get_setting("sub_lang", "English"),
        # Translate API (opsional). User isi via settings panel. Fallback ke
        # MyMemory kalau kosong. translate_apikey tidak pernah di-log.
        "translate_apikey": await get_setting("translate_apikey", ""),
        "translate_model": await get_setting("translate_model", "gemini-3.1-flash-lite"),
        "translate_apiurl": await get_setting("translate_apiurl", "https://generativelanguage.googleapis.com/v1beta/openai"),
    })

@app.post("/api/settings")
async def set_set(body: dict = None):
    body = body or {}
    for k in ("quality", "mode", "player", "sub_lang", "preferred_source",
              "translate_apikey", "translate_model", "translate_apiurl"):
        if k in body:
            val = body[k]
            if k == "translate_apikey" and isinstance(val, str):
                val = val.strip().strip("\"'").strip()
            await set_setting(k, val)
    return await get_set()

@app.get("/api/translate/logs")
async def get_translate_logs_api():
    """Mengambil riwayat log aktivitas translasi subtitle terbaru."""
    from api.translate import get_translate_logs
    return {"success": True, "data": {"logs": get_translate_logs()}}

app.mount("/js", StaticFiles(directory=os.path.join(frontend_dir, "js")), name="js")
app.mount("/css", StaticFiles(directory=os.path.join(frontend_dir, "css")), name="css")

@app.get("/")
async def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT, loop="asyncio", http="h11")
