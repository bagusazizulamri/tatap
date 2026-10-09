"""Scraper dan resolver stream untuk Otakudesu (Secondary Source Tatap).
Mengambil episode dan mendekripsi stream HLS dari player embed putarin.xyz (AES-256-GCM).
"""

import re
import json
import base64
import urllib.parse
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import OTAKU_BASE, HI_UA

HEADERS = {
    "User-Agent": HI_UA,
    "Referer": OTAKU_BASE + "/",
}

_otaku_client = None

def _get_otaku_client():
    global _otaku_client
    if _otaku_client is None:
        import httpx
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0)
        _otaku_client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(12.0, connect=5.0),
            limits=limits,
            headers=HEADERS
        )
    return _otaku_client

def _fetch(url: str, referer: str = None, timeout: int = 12) -> str:
    """Fetch helper menggunakan curl_cffi dengan fallback httpx pool dan TLS desync."""
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, headers=h, impersonate="chrome124", timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    try:
        client = _get_otaku_client()
        r = client.get(url, headers=h)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    # Fallback TLS Desync jika diblokir ISP
    try:
        from api.desync import tls_desync_request
        raw = tls_desync_request(url, headers=h, timeout=timeout)
        txt = raw.decode("utf-8", errors="replace")
        if txt and ("<html" in txt.lower() or "{" in txt):
            return txt
    except Exception:
        pass

    raise RuntimeError(f"Gagal memuat URL dari Otakudesu: {url}")


def search(query: str, limit: int = 10) -> list:
    """Cari anime di Otakudesu. Return [{title, url, id, poster}]."""
    clean_q = re.sub(r"[^\w\s-]", "", query).strip()
    url = f"{OTAKU_BASE}/?s={urllib.parse.quote_plus(clean_q)}&post_type=anime"
    html = _fetch(url)
    
    # Format kartu di otakudesu: <a class="ot-k" href="..."> ... <h2 class="ot-k-j">Title</h2>
    cards = re.findall(r'<a class="ot-k"\s+href="([^"]+)">.*?<img[^>]*src="([^"]+)".*?<h2 class="ot-k-j">([^<]+)</h2>', html, re.S)
    results = []
    for href, poster, title in cards[:limit]:
        title = title.strip()
        slug_m = re.search(r'/anime/([^/]+)/?', href)
        slug = slug_m.group(1) if slug_m else href
        results.append({
            "title": title,
            "url": href,
            "id": slug,
            "poster": poster,
        })
    return results


def get_episodes(anime_url_or_slug: str) -> list:
    """Ambil daftar episode untuk anime Otakudesu.
    Return [{ep: 1, title: 'Episode 1', url: 'https://...'}] urut dari ep 1 ke atas.
    """
    if anime_url_or_slug.startswith("http"):
        url = anime_url_or_slug
    else:
        url = f"{OTAKU_BASE}/anime/{anime_url_or_slug.strip('/')}/"

    html = _fetch(url)
    # Match: <a class="ot-ep" href="..."><span>Naruto Episode 1</span></a>
    eps_raw = re.findall(r'<a class="ot-ep"\s+href="([^"]+)">\s*<span>([^<]+)</span>', html)
    out = []
    seen = set()
    for href, title in eps_raw:
        if href in seen:
            continue
        seen.add(href)
        # Parse nomor episode dari title
        ep_num_m = re.search(r'(?:episode|eps|ep)\s*#?\s*(\d+)', title, re.I)
        ep_no = int(ep_num_m.group(1)) if ep_num_m else len(out) + 1
        out.append({
            "ep": ep_no,
            "title": title.strip(),
            "url": href
        })

    # Urutkan episode dari yang terkecil
    out.sort(key=lambda x: x["ep"])
    return out


def _decrypt_putarin_config(embed_url: str) -> dict:
    """Buka iframe embed putarin, ambil nonce & key, lalu dekripsi config AES-256-GCM."""
    html = _fetch(embed_url, referer=OTAKU_BASE + "/")
    px_m = re.search(r'window\.__PX\s*=\s*({[^<]+});', html)
    if not px_m:
        raise RuntimeError("Embed player token (__PX) tidak ditemukan")

    px = json.loads(px_m.group(1))
    nonce = px["n"]
    ciphertext_b64 = px["d"]

    # Ambil origin host dari embed_url (misal https://putarin.biz atau https://putarin.xyz)
    parsed_embed = urllib.parse.urlparse(embed_url)
    origin = f"{parsed_embed.scheme}://{parsed_embed.netloc}"

    # Ambil kunci AES dari /api/pk?n={nonce}
    key_url = f"{origin}/api/pk?n={urllib.parse.quote(nonce)}"
    key_hex = _fetch(key_url, referer=embed_url).strip()
    if len(key_hex) < 64:
        raise RuntimeError("Kunci dekripsi stream tidak valid")

    key_bytes = bytes.fromhex(key_hex)
    raw_data = base64.b64decode(ciphertext_b64)
    iv = raw_data[:12]
    ct = raw_data[12:]

    aesgcm = AESGCM(key_bytes)
    decrypted_bytes = aesgcm.decrypt(iv, ct, None)
    config = json.loads(decrypted_bytes.decode("utf-8"))
    config["_origin"] = origin
    return config


def resolve_stream(title_or_slug: str, ep: int = 1) -> dict:
    """Selesaikan URL stream m3u8 Otakudesu untuk anime & episode tertentu.
    Return dict terstandar dengan master m3u8, variants, referer, server name, dsb.
    """
    # 1. Cari anime jika bukan direct URL
    episodes = []
    if "otakudesu" in title_or_slug and "/anime/" in title_or_slug:
        episodes = get_episodes(title_or_slug)
    else:
        # Bersihkan slug atau judul (cth: "attack-on-titan-season-3-866" -> "attack on titan season 3")
        clean_title = re.sub(r'-\d+$', '', title_or_slug).replace("-", " ")
        search_res = search(clean_title)
        if not search_res:
            # Coba kata kunci pertama
            words = clean_title.split()
            if words:
                search_res = search(words[0])
        if not search_res:
            raise RuntimeError(f"Anime '{title_or_slug}' tidak ditemukan di Otakudesu")

        # Ambil episode dari hasil pencarian teratas
        episodes = get_episodes(search_res[0]["url"])

    if not episodes:
        raise RuntimeError("Tidak ada daftar episode di Otakudesu")

    # Cari episode yang cocok
    target_ep = next((e for e in episodes if e["ep"] == int(ep)), None)
    if not target_ep:
        # Fallback ke index jika nomor episode off
        idx = int(ep) - 1
        if 0 <= idx < len(episodes):
            target_ep = episodes[idx]
        else:
            raise RuntimeError(f"Episode {ep} belum rilis di Otakudesu")

    # 2. Ambil halaman episode dan ekstrak embed putarin
    ep_html = _fetch(target_ep["url"], referer=OTAKU_BASE + "/")
    iframe_m = re.search(r'<iframe[^>]*src="([^"]*putarin\.[a-z]+/e/[^"]+)"', ep_html)
    if not iframe_m:
        # Fallback regex untuk iframe apapun di dalam .ot-player
        iframe_m = re.search(r'<div class="ot-player"[^>]*>.*?<iframe[^>]*src="([^"]+)"', ep_html, re.S)
    if not iframe_m:
        raise RuntimeError("Iframe embed pemutar Otakudesu tidak ditemukan")

    embed_url = iframe_m.group(1)
    if embed_url.startswith("//"):
        embed_url = "https:" + embed_url

    # 3. Dekripsi player config putarin
    cfg = _decrypt_putarin_config(embed_url)
    origin = cfg.get("_origin", "https://putarin.xyz")
    hls_rel = cfg.get("file") or (cfg.get("sources") or [{}])[0].get("file")
    if not hls_rel:
        raise RuntimeError("File stream tidak ditemukan di konfigurasi putarin")

    hls_master = urllib.parse.urljoin(origin, hls_rel)

    # 4. Validasi master playlist & ekstrak variants
    variants = [
        {"q": "720p", "url": hls_master},
        {"q": "auto", "url": hls_master}
    ]

    return {
        "master": hls_master,
        "variants": variants,
        "sub": None,
        "sub_lang": "Indonesian (Hardsub)",
        "referer": origin + "/",
        "server": "Otakudesu (Sub Indo)",
        "source": "otakudesu",
        "tracks": [],
        "subtitles": [],
    }
