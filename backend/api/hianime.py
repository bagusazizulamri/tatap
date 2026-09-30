"""Port alur browse-and-play hianime.at (terinspirasi cara kerja pemain CLI)."""
import os, sys, re, json, base64, html as htmlmod
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HI_BASE, HI_UA, XOR_KEY

SEARCH_API = HI_BASE + "/search?keyword={}"
EPISODES_API = HI_BASE + "/api/theme/episode/list/{}"
SERVERS_API = HI_BASE + "/api/theme/episode/servers?episodeId={}"
BROWSE_API = HI_BASE + "/browse"

FILTERS = {
    "type": ["tv", "movie", "ova", "ona", "special", "music"],
    "status": ["releasing", "completed", "not_yet_aired"],
    "rating": ["g", "pg", "pg_13", "r_17", "r_plus", "rx"],
    "score": ["10", "9", "8", "7", "6", "5", "4", "3", "2", "1"],
    "season": ["spring", "summer", "fall", "winter"],
    "language": ["sub", "dub"],
    "sort": ["popularity", "trending", "score", "latest", "az", "most_favorite"],
}


def browse(params: dict = None, page: int = 1):
    """GET /browse?{filter} — kartu + total halaman. Maksimal sesuai form filter."""
    from urllib.parse import urlencode
    q = dict(params or {})
    q["page"] = max(1, int(page or 1))
    clean = {}
    for k, v in q.items():
        if k == "page":
            clean[k] = v
            continue
        v = str(v or "").strip().lower()
        if not v:
            continue
        if k in FILTERS and v in FILTERS[k]:
            clean[k] = v
        elif k in ("keyword", "sy", "sm", "ey", "em", "genre"):
            clean[k] = v
    url = BROWSE_API + "?" + urlencode(clean)
    page_html = _fetch(url)
    items = _parse_browse_cards(page_html)
    last = 1
    for m in re.finditer(r"page=(\d+)", page_html):
        try:
            last = max(last, int(m.group(1)))
        except ValueError:
            pass
    return {"items": items, "page": clean["page"], "total_pages": last, "params": clean}


def _parse_browse_cards(html: str):
    blocks = html.split("flw-item")
    out = []
    for b in blocks[1:]:
        m = re.search(r"film-name.*?href=\"[^\"]*/([^\"]+)\"[^>]*title=\"([^\"]*)\"", b, re.S)
        if not m:
            continue
        slug = m.group(1)
        if slug.startswith("watch/"):
            slug = slug[len("watch/"):]
        title = _clean(m.group(2))
        img = re.search(r"<img[^>]*src=\"([^\"]+)\"", b)
        poster = img.group(1) if img else ""
        sub = re.search(r"tick-sub.*?(\d+)<", b, re.S)
        dub = re.search(r"tick-dub.*?(\d+)<", b, re.S)
        eps = re.search(r"tick-eps.*?(\d+)<", b, re.S)
        typ = re.search(r"fdi-item\">(TV|Movie|OVA|ONA|Special|Music)<", b)
        dur = re.search(r"fdi-duration\">([^<]*)<", b)
        desc = re.search(r"class=\"description\">(.*?)</div>", b, re.S)
        out.append({
            "id": slug, "title": title,
            "poster": poster,
            "sub": int(sub.group(1)) if sub else 0,
            "dub": int(dub.group(1)) if dub else 0,
            "eps": int(eps.group(1)) if eps else 0,
            "type": typ.group(1) if typ else "",
            "duration": _clean(dur.group(1)) if dur else "",
            "synopsis": _clean(re.sub(r"<[^>]+>", "", desc.group(1)))[:220] if desc else "",
        })
    return out

def _failover_proxies():
    """Direct dulu, warp proxy hanya failover. Urutan: [tanpa proxy, warp proxy]."""
    import os
    out = [None]
    host = os.getenv("WARP_PROXY", "").strip()
    if host:
        if "://" not in host:
            host = "http://" + host
        out.append({"http": host, "https": host})
    return out


def _fetch(url, referer=None, timeout=15):
    last_err = ""
    for px in _failover_proxies():
        try:
            from curl_cffi import requests as creq
            try:
                kw = dict(headers={"User-Agent": HI_UA, "Accept": "text/html,application/json,*/*", **({"Referer": referer} if referer else {})}, impersonate="chrome124", timeout=timeout)
                if px:
                    kw["proxies"] = px
                r = creq.get(url, **kw)
                if r.status_code == 200:
                    return r.text
                if "Just a moment" in r.text or "cf-challenge" in r.text:
                    last_err = "Blocked by cloudflare (cf-challenge). Coba lagi nanti."
                    continue
                last_err = f"HTTP {r.status_code} from {url}"
                continue
            except Exception as e:
                last_err = str(e)
                continue
        except ImportError:
            last_err = "curl_cffi missing"
            break
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": HI_UA}) as c:
            h = {"Referer": referer} if referer else {}
            r = c.get(url, headers=h)
            if r.status_code == 200:
                return r.text
            raise RuntimeError(f"HTTP {r.status_code} from {url}")
    except Exception as e:
        raise RuntimeError(f"{last_err} | httpx: {e}")

def deobfuscate_blob(b64: str) -> str:
    raw = base64.b64decode(b64.strip())
    return bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(raw)).decode("utf-8", errors="strict")

def _clean(s: str) -> str:
    return htmlmod.unescape(s or "").strip()

def hianime_search(query: str, limit: int = 15):
    q = re.sub(r"\s+", "+", query.strip())
    page = _fetch(SEARCH_API.format(q))
    if "<title>Just a moment" in page:
        raise RuntimeError("Blocked by cloudflare.")
    page = page.split('id="main-sidebar"')[0]
    out = []
    for m in re.finditer(r'<h3 class="film-name">\s*<a href="[^"]*/([^"/]*)"\s*title="([^"]*)"', page):
        slug, title = m.group(1), _clean(m.group(2))
        if slug and title and len(out) < limit:
            out.append({"id": slug, "title": title})
    return out

def hianime_episodes(slug: str):
    numeric = slug.rsplit("-", 1)[-1]
    page = _fetch(EPISODES_API.format(numeric)).replace("\\", "")
    eps = []
    for m in re.finditer(r'data-number="([^"]*)撃.*?data-id="([0-9]+)"', page):
        pass
    for m in re.finditer(r'data-number="([^"]*)"[^>]*data-id="([0-9]+)"', page):
        try:
            ep_no = int(m.group(1))
        except ValueError:
            continue
        eps.append({"ep": ep_no, "ep_id": m.group(2)})
    seen = {}
    for e in eps:
        seen[e["ep"]] = e["ep_id"]
    return [{"ep": k, "ep_id": v} for k, v in sorted(seen.items())]

def _parse_servers(html: str, mode: str):
    items = html.replace('\\"', '"').split("server-item")
    servers = []
    for it in items:
        if f'data-type="{mode}"' not in it:
            continue
        mh = re.search(r'data-hash="([^"]*)"', it)
        mn = re.search(r'data-server-name="([^"]*)"', it)
        if not mh:
            continue
        try:
            embed = base64.b64decode(mh.group(1)).decode("utf-8", errors="strict")
        except Exception:
            continue
        if not embed.startswith("http"):
            continue
        servers.append({"name": mn.group(1) if mn else "unknown", "embed": embed})
    def score(s):
        if "zokoanime" in s["name"].lower():
            return 0
        if "zokoanime.video" in s["embed"]:
            return 1
        if "megaplay" in s["embed"].lower():
            return 9
        return 5
    servers.sort(key=score)
    return servers

def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


MEGA_KEY = b"i?LMTAx0Q6,:}50U" + b"\x00" * 16
MEGA_IV = b"W0;27ToaUpl_P%'c"

# SegmentDecrypt (newclient.min.js): segmen playlist berbentuk /segment/{token}
# -> AES-CBC decrypt token -> URL .ts asli. Key/IV tertanam di JS.
SEG_KEY = MEGA_KEY
SEG_IV = MEGA_IV
SEG_RE = re.compile(r"/segment/([A-Za-z0-9_-]+)")
# SegmentStrip: 252 byte pertama segmen dari host ini dibuang
STRIP_BYTES = 252
STRIP_RE = re.compile(r"ibyteimg\.com|tiktokcdn\.com|ipstatp\.com|yoot\.akirax\.buzz", re.I)


def _mega_decrypt(enc: str) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    raw = _b64url_decode(enc.strip())
    d = Cipher(algorithms.AES(MEGA_KEY), modes.CBC(MEGA_IV)).decryptor()
    pt = d.update(raw) + d.finalize()
    # strip PKCS7-ish padding
    pad = pt[-1] if pt else 0
    if 1 <= pad <= 16 and all(b == pad for b in pt[-pad:]):
        pt = pt[:-pad]
    return pt.decode("utf-8", errors="strict")


def _try_megaplay(embed: str):
    """embed = https://megaplay.buzz/stream/s-2/{realid}/{sub|dub}.
    Flow (from newclient.min.js): GET embed page -> data-id -> GET
    /stream/getSourcesNew?id={data-id} (Referer=embed) -> {enc} ->
    AES-CBC decrypt -> {file: master.m3u8} + tracks[]."""
    page = _fetch(embed, referer="https://hianime.at/")
    m = re.search(r'data-id="(\d+)"', page)
    if not m:
        raise RuntimeError("megaplay data-id not found")
    data_id = m.group(1)
    origin = re.sub(r"^(https?://[^/]*).*", r"\1", embed)
    api_url = origin + f"/stream/getSourcesNew?id={data_id}"
    try:
        txt = _fetch(api_url, referer=embed)
    except Exception:
        txt = _fetch(origin + f"/stream/getSources?id={data_id}", referer=embed)
    cfg = json.loads(txt)
    master = ""
    if isinstance(cfg.get("sources"), list) and cfg["sources"]:
        master = cfg["sources"][0].get("file", "")
    elif isinstance(cfg.get("sources"), dict):
        master = cfg["sources"].get("file", "")
    if not master and cfg.get("enc"):
        dec = json.loads(_mega_decrypt(cfg["enc"]))
        master = dec.get("file", "")
    if not master:
        raise RuntimeError("getSources gave no file")
    # master may be relative
    if master.startswith("/"):
        master = origin + master
    subs = cfg.get("tracks") or []
    default = next((s for s in subs if s.get("default")), subs[0] if subs else None)
    variants = []
    try:
        text = _fetch(master, referer=origin + "/")
        base = master.rsplit("/", 1)[0] + "/"
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                rm = re.search(r"RESOLUTION=\d+x(\d+)", ln)
                q = (rm.group(1) + "p") if rm else "auto"
                url = (lines[i + 1].strip() if i + 1 < len(lines) else "")
                if url and not url.startswith("#"):
                    if not url.startswith("http"):
                        url = base + url
                    variants.append({"q": q, "url": url})
    except Exception:
        pass
    variants.sort(key=lambda v: int(re.sub(r"\D", "", v["q"]) or 0), reverse=True)
    if not variants:
        variants = [{"q": "auto", "url": master}]
    return {"master": master, "variants": variants,
            "sub": (default.get("src") or default.get("file")) if default else None,
            "sub_lang": (default.get("label") or default.get("lang")) if default else None,
            "referer": origin + "/", "mal_id": "",
            "tracks": subs}

def _order_servers(servers):
    def score(s):
        n, e = s["name"].lower(), s["embed"].lower()
        if "zokoanime" in n and "zokoanime.video" in e:
            return 0
        if "megaplay" in e:
            return 5
        return 9
    return sorted(servers, key=score)


def _try_embed_legacy(embed: str):
    referer = re.sub(r"^(https?://[^/]*).*", r"\1/", embed)
    page = _fetch(embed)
    m = re.search(r'window\.__P="([^"]*)"', page)
    if not m:
        raise RuntimeError("window.__P not found")
    try:
        cfg = json.loads(deobfuscate_blob(m.group(1)))
    except Exception:
        raise RuntimeError("deobfuscate failed")
    master = cfg.get("src") or ""
    if not master and isinstance(cfg.get("sources"), list) and cfg["sources"]:
        master = cfg["sources"][0].get("src", "")
    if ".m3u8" not in master:
        return None
    subs = cfg.get("subtitles") or []
    default = next((s for s in subs if s.get("default")), subs[0] if subs else None)
    variants = []
    try:
        text = _fetch(master, referer=referer)
        base = master.rsplit("/", 1)[0] + "/"
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                rm = re.search(r"RESOLUTION=\d+x(\d+)", ln)
                q = (rm.group(1) + "p") if rm else "auto"
                url = (lines[i + 1].strip() if i + 1 < len(lines) else "")
                if url and not url.startswith("#"):
                    if not url.startswith("http"):
                        url = base + url
                    variants.append({"q": q, "url": url})
    except Exception:
        pass
    variants.sort(key=lambda v: int(re.sub(r"\D", "", v["q"]) or 0), reverse=True)
    if not variants:
        variants = [{"q": "auto", "url": master}]
    mal_id = ""
    mm = re.search(r"/mal/([0-9]+)/", embed)
    if mm:
        mal_id = mm.group(1)
    return {"master": master, "variants": variants, "sub": (default.get("src") or default.get("file")) if default else None, "sub_lang": (default.get("label") or default.get("lang")) if default else None, "referer": referer, "mal_id": mal_id}

def hianime_m3u8(episode_maps, ep_no: int, mode: str = "sub"):
    mode = "dub" if str(mode).lower() == "dub" else "sub"
    ep_id = None
    for e in episode_maps:
        if int(e["ep"]) == int(ep_no):
            ep_id = e["ep_id"]
            break
    if not ep_id:
        raise RuntimeError(f"Episode {ep_no} not released!")
    servers_html = _fetch(SERVERS_API.format(ep_id))
    servers = _order_servers(_parse_servers(servers_html, mode))
    if not servers:
        raise RuntimeError(f"No {mode} server found for ep {ep_no}")
    last_err = ""
    for srv in servers:
        try:
            if "zokoanime.video" in srv["embed"].lower():
                got = _try_embed_legacy(srv["embed"])
            else:
                got = _try_megaplay(srv["embed"])
            if got:
                got["server"] = srv["name"]
                return got
            last_err = f"embed {srv['name']} gave no m3u8"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(last_err or "m3u8 not found")

def select_quality(variants, quality: str = "best"):
    if not variants:
        raise RuntimeError("no variants")
    q = (quality or "best").lower()
    if q == "best":
        return variants[0]
    if q == "worst":
        nums = [v for v in variants if re.match(r"^\d+", v["q"])]
        return nums[-1] if nums else variants[-1]
    for v in variants:
        if v["q"].lower() == q or v["q"].lower().startswith(q):
            return v
    return variants[0]
