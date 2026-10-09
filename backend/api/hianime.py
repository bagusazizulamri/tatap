"""Port alur browse-and-play hianime.at (terinspirasi cara kerja pemain CLI)."""
import os, sys, re, json, base64, html as htmlmod, threading, time as _time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HI_BASE, HI_UA, XOR_KEY

SEARCH_API = HI_BASE + "/search?keyword={}"
EPISODES_API = HI_BASE + "/api/theme/episode/list/{}"
SERVERS_API = HI_BASE + "/api/theme/episode/servers?episodeId={}"
BROWSE_API = HI_BASE + "/browse"

# Negative cache:
#   _neg_cache        : host -> expires_at_epoch (host mati global, skip semua)
#   _neg_pair_cache   : (host|slug|ep) -> expires_at_epoch (host mati untuk episode
#                       spesifik, misal zokoanime 404 untuk anime baru)
# TTL default 1 jam. Per-(host,slug,ep) cache bikin request berikut langsung skip
# server yang tidak punya episode tsb, tanpa biaya probe network.
# Catatan: per Oct 2026, hls.dramahot.top (CDN ZokoAnime) sudah bisa dijangkau
# lagi (TLS handshake sukses, HTTP 404 untuk path dummy). Tidak masuk _DEAD_HOSTS.
# Kalau host mati lagi nanti, _mark_dead() akan menambahkannya otomatis via
# negative cache (lihat _probe_master()).
_DEAD_HOSTS = set()  # daftar host yang SELALU dianggap mati (skip probe).

_neg_lock = threading.Lock()
_neg_cache = {}        # host -> expires_at_epoch
_neg_pair_cache = {}   # "host|slug|ep" -> expires_at_epoch


def _is_dead_host(host):
    base = (host or "").lower()
    for d in _DEAD_HOSTS:
        if d in base:
            return True
    with _neg_lock:
        exp = _neg_cache.get(base)
        if exp and exp > _time.time():
            return True
    return False


def _is_dead_pair(host, slug, ep):
    """Cek negative cache per-(host, slug, ep)."""
    base = (host or "").lower()
    key = f"{base}|{slug or ''}|{ep}"
    with _neg_lock:
        exp = _neg_pair_cache.get(key)
        return bool(exp and exp > _time.time())


def _mark_dead(host, ttl=300):
    base = (host or "").lower()
    with _neg_lock:
        _neg_cache[base] = int(_time.time()) + ttl


def _mark_dead_pair(host, slug, ep, ttl=600):
    """Tandai (host, slug, ep) gagal. Request berikut skip tanpa probe (TTL 10 menit agar pulih jika CDN update)."""
    base = (host or "").lower()
    key = f"{base}|{slug or ''}|{ep}"
    with _neg_lock:
        _neg_pair_cache[key] = int(_time.time()) + ttl


def _host_from(url):
    m = re.match(r"https?://([^/]+)", url or "", re.I)
    return m.group(1).lower() if m else ""


_BLOCKED_DPI_HOSTS = {"hls.dramahot.top"}


def _probe_master(master_url, referer):
    """Probe cepat master.m3u8:
    100% Direct TCP port 443 tanpa VPN.
    Bypass DPI ISP menggunakan TLS Client-Hello record fragmentation (desync)."""
    if not master_url or not master_url.startswith("http"):
        raise RuntimeError("invalid master url")
    host = _host_from(master_url)
    if _is_dead_host(host):
        raise RuntimeError(f"host dead: {host}")
    headers = {"User-Agent": HI_UA,
               **({"Referer": referer} if referer else {})}
    
    # Jika host terdeteksi diblokir DPI ISP, gunakan TLS desync langsung
    if host in _BLOCKED_DPI_HOSTS:
        try:
            from api.desync import tls_desync_request
            content = tls_desync_request(master_url, headers=headers, timeout=8.0)
            if content and b"#EXTM3U" in content:
                return content
        except Exception:
            pass

    # Direct connection biasa untuk semua host normal
    try:
        from curl_cffi import requests as creq
        kw = dict(headers=headers, impersonate="chrome124", timeout=10)
        r = creq.get(master_url, **kw)
        if r.status_code == 200 and r.content:
            return r.content
        if r.status_code >= 400:
            raise RuntimeError(f"upstream {r.status_code} for {host}")
    except Exception as e:
        err_str = str(e).lower()
        if "reset" in err_str or "ssl" in err_str or "recv failure" in err_str:
            _BLOCKED_DPI_HOSTS.add(host)
            try:
                from api.desync import tls_desync_request
                content = tls_desync_request(master_url, headers=headers, timeout=8.0)
                if content and b"#EXTM3U" in content:
                    return content
            except Exception:
                pass
        _mark_dead(host)
        raise RuntimeError(f"probe fail {host}: {type(e).__name__}")

FILTERS = {
    "type": ["tv", "movie", "ova", "ona", "special", "music"],
    "status": ["releasing", "completed", "not_yet_aired"],
    "rating": ["g", "pg", "pg_13", "r_17", "r_plus", "rx"],
    "score": ["10", "9", "8", "7", "6", "5", "4", "3", "2", "1"],
    "season": ["spring", "summer", "fall", "winter"],
    "language": ["sub", "dub"],
    "sort": ["popularity", "trending", "score", "latest", "az", "most_favorite"],
}


def scrape_genres():
    """Ambil list genre dari sidebar widget hianime /browse. Return [{slug,title}]."""
    html = _fetch(BROWSE_API)
    out, seen = [], set()
    for m in re.finditer(
        r'<a href="https?://hianime\.at/genres/([a-z0-9-]+)"\s+title="([^"]+)"',
        html):
        slug = m.group(1)
        title = htmlmod.unescape(m.group(2)).strip()
        if slug in seen or not slug or not title:
            continue
        seen.add(slug)
        out.append({"slug": slug, "title": title})
    return out


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
        n, e = s["name"].lower(), s["embed"].lower()
        if "megaplay" in e:
            return 0
        if "zokoanime.video" in e:
            return 5
        if "zokoanime" in n:
            return 6
        return 9
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


def _normalize_subtitles(raw_tracks, referer: str = ""):
    """Normalisasi track subtitle mentah (Megaplay 'tracks[]' / ZokoAnime 'subtitles')
    menjadi list[{label, lang, url, default}] yang siap kirim ke client.

    - Filter track yang bukan subtitle (kind=thumbnails, kind=video, dsb.).
    - Kalau ada track kind=subtitle tanpa URL (referensi internal), pakai default.
    - Field 'label' diprioritaskan, fallback ke 'lang', fallback ke "Subtitle N".
    - Hanya track yang punya URL http(s) masuk output.
    - Validasi ringan: kalau ada URL, biarkan apa adanya (soft-validate oleh caller).
    Soft validate subtitle tidak dilakukan di sini supaya tidak menambah latency
    saat scrape multi-track; validasi per-track dilakukan saat user memilihnya.
    """
    out = []
    if not raw_tracks or not isinstance(raw_tracks, list):
        return out
    # Helper: ubah URL relatif jadi absolut terhadap referer.
    def _abs(u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            # protocol-relative → pakai scheme dari referer (biasanya https).
            return "https:" + u
        if u.startswith("/") and referer:
            m = re.match(r"^(https?://[^/]+)", referer)
            if m:
                return m.group(1) + u
        return u
    for i, t in enumerate(raw_tracks):
        if not isinstance(t, dict):
            continue
        # Skip non-subtitle tracks (thumbnail, video, audio descriptions, dll.).
        kind = (t.get("kind") or "").lower()
        if kind and kind not in ("subtitles", "subtitle", "captions", "caption"):
            continue
        # Megaplay/Zokoanime kadang pakai 'src' atau 'file' untuk URL subtitle.
        url = _abs(t.get("src") or t.get("file") or t.get("url") or "")
        if not url or not url.startswith("http"):
            continue
        label = (t.get("label") or t.get("lang") or t.get("language")
                 or f"Subtitle {i + 1}").strip()
        # Kalau label = kode bahasa (id, en), ganti jadi nama readable.
        if len(label) <= 3 and label.lower() in _LANG_NAME:
            label = _LANG_NAME[label.lower()]
        inferred = _label_to_lang(label)
        lang = inferred or (t.get("lang") or t.get("language") or t.get("srclang") or "").strip().lower()
        is_def = bool(t.get("default")) or bool(t.get("is_default")) or False
        out.append({
            "label": label,
            "lang": lang,
            "url": url,
            "default": is_def,
        })
    # Pastikan tepat satu track 'default'. Kalau tidak ada, prioritaskan English, fallback ke track pertama.
    has_def = any(o["default"] for o in out)
    if out and not has_def:
        en_track = next((o for o in out if (o.get("lang") or "").lower() == "en" or (o.get("label") or "").lower().startswith("english")), None)
        if en_track:
            en_track["default"] = True
        else:
            out[0]["default"] = True
    return out


# Peta kode bahasa 2-3 char → nama readable (untuk label dropdown).
_LANG_NAME = {
    "en": "English", "eng": "English",
    "id": "Indonesian", "ind": "Indonesian",
    "ja": "Japanese", "jpn": "Japanese",
    "es": "Spanish", "spa": "Spanish",
    "pt": "Portuguese", "por": "Portuguese",
    "fr": "French", "fra": "French", "fre": "French",
    "de": "German", "deu": "German", "ger": "German",
    "it": "Italian", "ita": "Italian",
    "ko": "Korean", "kor": "Korean",
    "zh": "Chinese", "chi": "Chinese", "zho": "Chinese",
    "ar": "Arabic", "ara": "Arabic",
    "ru": "Russian", "rus": "Russian",
    "th": "Thai", "tha": "Thai",
    "vi": "Vietnamese", "vie": "Vietnamese",
    "tr": "Turkish", "tur": "Turkish",
    "hi": "Hindi", "hin": "Hindi",
}


def _label_to_lang(label):
    """Infer kode bahasa dari label (case-insensitive exact match).
    Dipakai sebagai fallback kalau track tidak punya field lang/srclang."""
    if not label:
        return ""
    lab = label.strip()
    # Cek exact match nama readable.
    for code, name in _LANG_NAME.items():
        if len(code) == 2 and name.lower() == lab.lower():
            return code
    # Cek 3-letter prefix (misal "English (US)" → "eng"/"en").
    low = lab.lower()
    for code in ("en", "id", "ja", "es", "pt", "fr", "de", "it", "ko", "zh",
                 "ar", "ru", "th", "vi", "tr", "hi"):
        if low.startswith(code + " ") or low.startswith(code + "(") or low == code:
            return code
    return ""


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
    default = next((s for s in subs if s.get("default") or s.get("is_default")), None)
    if not default and subs:
        default = next((s for s in subs if (s.get("lang") or "").lower() == "en" or (s.get("label") or "").lower().startswith("english")), subs[0])
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
    # Probe master — kalau host mati, return None (bukan raise) supaya caller
    # smart-fallback ke server berikutnya.
    try:
        _probe_master(master, referer=origin + "/")
    except Exception as e:
        raise RuntimeError(f"megaplay probe: {e}")
    # Validasi playlist: minimal ada 1 segment/variant URL agar HLS.js tidak hang.
    try:
        variants = _validate_master_playlist(master, referer=origin + "/", variants=variants)
    except Exception as e:
        raise RuntimeError(f"megaplay playlist: {e}")
    # Soft-validasi subtitle (tidak memblokir kalau invalid).
    sub_url = (default.get("src") or default.get("file")) if default else None
    if sub_url:
        sub_url = _validate_sub_url(sub_url, referer=origin + "/")
    # Multi-subtitle: normalisasi seluruh tracks Megaplay untuk dropdown.
    subtitles = _normalize_subtitles(subs, referer=origin + "/")
    return {"master": master, "variants": variants,
            "sub": sub_url,
            "sub_lang": (default.get("label") or default.get("lang")) if default else None,
            "referer": origin + "/", "mal_id": "",
            "tracks": subs,
            "subtitles": subtitles}

def _order_servers(servers):
    def score(s):
        n, e = s["name"].lower(), s["embed"].lower()
        # Megaplay dulu: lebih stabil & tidak bergantung CDN dramahot.top.
        if "megaplay" in e:
            return 0
        if "zokoanime.video" in e:
            return 5
        if "zokoanime" in n:
            return 6
        return 9
    return sorted(servers, key=score)


def _fetch_media(url: str, referer: str = None, timeout: int = 10) -> str:
    """Fetch teks/playlist/sub:
    - Host biasa: 100% direct.
    - Host terblokir ISP: bypass via TLS desync tanpa VPN."""
    host = _host_from(url)
    headers = {"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}
    if host in _BLOCKED_DPI_HOSTS:
        try:
            from api.desync import tls_desync_request
            b = tls_desync_request(url, headers=headers, timeout=timeout)
            if b:
                return b.decode("utf-8", errors="ignore")
        except Exception:
            pass
    try:
        from curl_cffi import requests as creq
        kw = dict(headers=headers, impersonate="chrome124", timeout=timeout)
        r = creq.get(url, **kw)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return _fetch(url, referer=referer, timeout=timeout)


def _validate_master_playlist(master_url: str, referer: str, variants: list):
    """Validasi master playlist: harus (a) mulainya #EXTM3U, (b) minimal ada 1
    URL segment/variant pada body. Return list variants yang sudah tervalidasi:
    - Kalau caller sudah punya variants dan minimal 1 URL absolute → pakai itu.
    - Kalau tidak, fallback ke single-variant dari master playlist.
    Raise RuntimeError kalau playlist tidak punya konten yang bisa diputar."""
    if not master_url or not master_url.startswith("http"):
        raise RuntimeError("invalid master url")
    body = _fetch_media(master_url, referer=referer, timeout=10)
    txt = body if isinstance(body, str) else body.decode("utf-8", errors="ignore")
    if "#EXTM3U" not in txt:
        raise RuntimeError("master playlist: not m3u8")
    # Hitung jumlah stream-inf / segment lines yang valid.
    base = master_url.rsplit("/", 1)[0] + "/"
    valid_count = 0
    lines = txt.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        # Absolute atau relative URL ke segment/variant playlist.
        if s.startswith("http") or "/" in s or s.endswith(".m3u8") or s.endswith(".ts"):
            valid_count += 1
    if valid_count == 0:
        raise RuntimeError("master playlist: no segments")
    # Caller punya variants (misal multi-bitrate dari megaplay) → filter URL valid.
    if variants:
        out = [v for v in variants if v.get("url", "").startswith("http")]
        if out:
            return out
    # Single-variant fallback: pakai master playlist langsung.
    return [{"q": "auto", "url": master_url}]


def _validate_sub_url(sub_url: str, referer: str):
    """Soft-validasi subtitle URL: HEAD/GET kecil, kalau 4xx/5xx atau body
    kosong → return None. Kalau 200 → return URL apa adanya.
    Subtitle yang invalid jangan memblokir playback."""
    if not sub_url or not sub_url.startswith("http"):
        return None
    try:
        host = _host_from(sub_url)
        headers = {"User-Agent": HI_UA, **({"Referer": referer} if referer else {})}
        if host in _BLOCKED_DPI_HOSTS:
            from api.desync import tls_desync_request
            b = tls_desync_request(sub_url, headers=headers, timeout=6.0)
            if b and len(b) >= 10:
                return sub_url
            return None
        from curl_cffi import requests as creq
        kw = dict(headers=headers, impersonate="chrome124", timeout=8)
        r = creq.get(sub_url, **kw)
        if r.status_code == 200 and r.content and len(r.content) >= 10:
            return sub_url
        return None
    except Exception:
        return None


def _try_embed_legacy(embed: str):
    referer = re.sub(r"^(https?://[^/]*).*", r"\1/", embed)
    page = _fetch(embed)
    # Deteksi halaman 404 ZokoAnime (server return HTML page, bukan markdown())
    # Page signature: ada "<title>Player</title>" + "Not" + "found." pada body.
    # Skip regex window.__P kalau 404 — raise sebagai "anime not on server"
    # sehingga caller skip server ini (jangan fallback dalam loop yang sama).
    if "<title>Player</title>" in page and "Not " in page and "found." in page:
        raise RuntimeError("404 page (anime not on server)")
    m = re.search(r'window\.__P\s*=\s*"([^"]*)"', page)
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
    # Probe master — kalau host mati, return None agar caller fall-through.
    try:
        _probe_master(master, referer=referer)
    except Exception as e:
        raise RuntimeError(f"zokoanime probe: {e}")
    # Validasi playlist: minimal ada 1 segment/variant URL agar HLS.js tidak hang.
    subs = cfg.get("subtitles") or []
    default = next((s for s in subs if s.get("default") or s.get("is_default")), None)
    if not default and subs:
        default = next((s for s in subs if (s.get("lang") or "").lower() == "en" or (s.get("label") or "").lower().startswith("english")), subs[0])
    try:
        variants = _validate_master_playlist(master, referer=referer, variants=[])
    except Exception as e:
        raise RuntimeError(f"zokoanime playlist: {e}")
    mal_id = ""
    mm = re.search(r"/mal/([0-9]+)/", embed)
    if mm:
        mal_id = mm.group(1)
    # Soft-validasi subtitle (tidak memblokir kalau invalid).
    sub_url = (default.get("src") or default.get("file")) if default else None
    if sub_url:
        sub_url = _validate_sub_url(sub_url, referer=referer)
    # Multi-subtitle: normalisasi seluruh tracks ZokoAnime untuk dropdown.
    subtitles = _normalize_subtitles(subs, referer=referer)
    return {"master": master, "variants": variants,
            "sub": sub_url,
            "sub_lang": (default.get("label") or default.get("lang")) if default else None,
            "referer": referer, "mal_id": mal_id,
            "subtitles": subtitles}

def hianime_m3u8(episode_maps, ep_no: int, mode: str = "sub", slug: str = ""):
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

    # Smart-fallback tier: megaplay dulu (HD-1, Vidstream-2), kalau gagal ke VidToglap
    # (vidtube.site), terakhir ke ZokoAnime.
    def tier_of(srv):
        e = srv["embed"].lower()
        if "megaplay" in e:
            return 0
        if "vidtube.site" in e:
            return 1
        if "zokoanime.video" in e:
            return 2
        return 3

    servers_sorted = sorted(servers, key=lambda sr: (tier_of(sr), sr["name"]))
    last_err = ""
    for srv in servers_sorted:
        host = _host_from(srv["embed"])
        # Skip host mati (global negative cache) tanpa re-fetch.
        if _is_dead_host(host):
            last_err = f"skip {srv['name']} (dead host)"
            continue
        # Skip per-(host, slug, ep): anime ini memang tidak ada di server ini
        # (misal ZokoAnime 404 untuk judul baru). Negative cache TTL 1 jam.
        if slug and _is_dead_pair(host, slug, ep_no):
            last_err = f"skip {srv['name']} (404 cached for ep {ep_no})"
            continue
        try:
            embed_low = srv["embed"].lower()
            if "zokoanime.video" in embed_low:
                got = _try_embed_legacy(srv["embed"])
            elif "vidtube.site" in embed_low or "vidplay" in srv["name"].lower():
                # VidPlay-1 (vidtube.site) juga pakai pola window.__P.
                got = _try_embed_legacy(srv["embed"])
            else:
                got = _try_megaplay(srv["embed"])
            if got:
                got["server"] = srv["name"]
                return got
            last_err = f"{srv['name']} gave no m3u8"
        except Exception as e:
            err_msg = str(e)
            last_err = f"{srv['name']}: {err_msg}"
            msg = err_msg.lower()
            # Tandai host mati kalau error-nya network (RST, ConnectError, probe fail).
            if any(t in msg for t in ("rst", "reset", "connect", "timeout", "dead", "upstream", "probe fail", "sslerror")):
                _mark_dead(host)
            # Tandai per-(host, slug, ep) kalau anime tidak ada di server ini.
            if any(t in msg for t in ("404 page", "not on server", "window.__p not found", "data-id not found")):
                if slug:
                    _mark_dead_pair(host, slug, ep_no)
            continue
    if "dramahot.top" in last_err.lower() or "zokoanime" in last_err.lower():
        raise RuntimeError(
            "Server video anime baru ini (ZokoAnime) diblokir DPI/ISP (hls.dramahot.top). "
            "Server utama (Megaplay) belum diunggah oleh penyedia. "
            "Aktifkan Cloudflare WARP (1.1.1.1) / VPN untuk memutar judul ini."
        )
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
