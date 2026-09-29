import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio, subprocess, tempfile
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from config import APP_PORT, APP_HOST, HI_BASE, HI_UA
from database import init_db, get_search_cache, set_search_cache, get_episode_cache, set_episode_cache, add_history, get_history, clear_history, get_setting, set_setting
from api import hianime as hi
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
    # SegmentDecrypt compat: playlist segmen .jpg/.html sebenarnya adalah
    # .ts yang di-strip 252 byte + URL ter-enkripsi -> decrypt di sini (server-side,
    # port dari newclient.min.js SegmentDecrypt + SegmentStrip).
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
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as c:
        r = await c.get(url, headers={"User-Agent": HI_UA, **({"Referer": referer} if referer else {})})
        body = r.content
        ctype = r.headers.get("content-type", "application/octet-stream")
        # rewrite playlist: /segment/TOKEN -> /api/player/video?url=... (decrypt next hop)
        # + segmen relatif -> absolut + lewat proxy
        try:
            txt = body.decode("utf-8", errors="strict")
            if "#EXTM3U" in txt:
                import urllib.parse as _up
                base = url.rsplit("/", 1)[0] + "/"
                out = []
                for ln in txt.splitlines():
                    s = ln.strip()
                    if not s or s.startswith("#"):
                        out.append(ln)
                        continue
                    absu = s if s.startswith("http") else _up.urljoin(base, s)
                    out.append(f"/api/player/video?url={_up.quote(absu, safe='')}&referer={_up.quote(referer or '', safe='')}")
                body = "\n".join(out).encode()
                ctype = "application/vnd.apple.mpegurl"
        except Exception:
            pass
        else:
            # segmen biner: strip STRIP_BYTES pertama bila host cocok (port SegmentStrip)
            try:
                if STRIP_RE.search(url) and len(body) > STRIP_BYTES:
                    body = body[STRIP_BYTES:]
            except Exception:
                pass
        h = {"Content-Type": ctype, "Access-Control-Allow-Origin": "*"}
        return Response(content=body, headers=h)

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
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
