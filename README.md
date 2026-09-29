# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, tanpa server publik. Jalan 100% di `127.0.0.1` milikmu sendiri.

## Kenapa namanya Tatap?

*tatap* (KBBI): memandang dengan mata terbuka lebar. Pas untuk app yang kerjanya satu: **menatap layar**. Tidak pakai embel-embel *ani-*, *-web*, *-term*, atau *-kun* yang sudah dipakai ratusan proyek lain.

## Sekilas

```
kamu --browser--> 127.0.0.1:8767 (Tatap)
  search / episodes / resolve
  --> hianime.at --> megaplay (Vidstream-2)
  getSourcesNew + AES-CBC decrypt (server-side)
  --> master.m3u8 --> proxy lokal --> video + hls.js
```

- **1 sumber katalog**: `hianime.at` (search + daftar episode, alur browse-and-play ala pemain CLI).
- **1 sumber stream**: embed `megaplay` yang di-decrypt di backend (Python `cryptography`, AES-CBC hasil bedah `newclient.min.js`), bukan di browser.
- **Semua video lewat proxy lokal** (`/api/player/video`) supaya header `Referer` terkirim dan tidak kena CORS.
- **Lokal-only**: bind `127.0.0.1`, tanpa Docker, tanpa auth, tanpa telemetry. History dan cache cukup di SQLite (`backend/anime.db`, WAL).

## Fitur

- Pencarian live (>=3 huruf, debounce 600ms), navigasi atas/bawah + Enter, recent chips (6 terakhir).
- Modal judul: toggle SUB/DUB, toggle quality, filter episode, badge sudah-ditonton.
- Modal player 16:9, spinner resolving/buffering, varian quality, PREV/NEXT, subtitle vtt.
- Ambient light di belakang video (bisa dimatikan), efek CRT scanlines (bisa dimatikan).
- Lanjutkan menonton (10 terakhir), shortcut keyboard, tombol putar di MPV lokal.

## Mulai cepat

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./run.sh
# buka http://127.0.0.1:8767
```

Ganti port bila bentrok:

```bash
APP_PORT=8888 APP_HOST=127.0.0.1 ./venv/bin/python backend/main.py
```

Butuh pemutar eksternal? `sudo apt install mpv`, lalu pakai tombol MPV di modal player.
## Struktur

```
tatap/
  run.sh                  # ./venv/bin/python backend/main.py (foreground, Ctrl+C stop)
  requirements.txt        # fastapi, uvicorn, aiosqlite, httpx, curl_cffi, cryptography, dotenv
  backend/
    main.py             # FastAPI: 8 endpoint + proxy video/sub + play-mpv + history
    config.py           # HI_BASE, HI_UA, XOR_KEY, key/IV AES megaplay, DB path
    anime.db            # SQLite WAL (dibuat otomatis saat pertama jalan)
    api/hianime.py      # search / episodes / servers / megaplay-decrypt / select_quality
    database/__init__.py# search_cache, episode_cache, watch_history, settings
  frontend/
    index.html          # topbar + search + modal judul + modal player
    css/style.css         # tema gelap, CRT, ambient, modal, responsif
    js/api.js             # window.Tatap (fetch ke /api)
    js/app.js             # alur search, judul, episode, player, ambient, shortcut
    js/vendor/hls.min.js
  cache/                  # file sementara, aman dihapus kapan saja
```

## API ringkas

Semua response `{success: true, data: ...}`.

```
GET  /api/health
GET  /api/search?q=frieren
GET  /api/anime/{slug}/episodes
GET  /api/stream/resolve?slug=&ep=&mode=&q=
GET  /api/player/video?url=&referer=
GET  /api/player/sub?url=&referer=
POST /api/play-mpv  {slug,ep,mode,quality}
GET  /api/history, POST /api/history, DELETE /api/history
GET  /api/settings, POST /api/settings
GET  /  /js/*  /css/*
```

## Cara kerja stream

1. Search: `GET /search?keyword=` lalu parse `h3.film-name > a` menjadi `{slug, title}`.
2. Episodes: angka belakang slug menjadi `GET /api/theme/episode/list/{id}` menjadi `{ep -> ep_id}`.
3. Servers: `GET /api/theme/episode/servers?episodeId=` lalu ambil `data-hash` (base64 ke URL megaplay).
4. Decrypt: `GET` halaman embed ambil `data-id`, lalu `GET /stream/getSourcesNew?id=` dengan Referer embed, decrypt `{enc}` via AES-CBC menjadi `master.m3u8` + subtitle.
5. Varian: parse `#EXT-X-STREAM-INF` + `RESOLUTION` menjadi 1080p/720p, sort descending.
6. Play: `hls.js` lewat `/api/player/video?url=` dengan Referer terkirim, rewrite URL relatif, decrypt token `/segment/` bila ada.

Cache: `search_cache` 24 jam, `episode_cache` 12 jam. Segmen `.ts` tidak disimpan ke disk.

## Batasan

- Katalog dan stream milik pihak ketiga. Bila hulu ganti player atau Cloudflare, resolve gagal dengan pesan jujur.
- Subtitle mengikuti yang disediakan hulu (umumnya Inggris).
- Jangan expose ke internet / 0.0.0.0. Tidak ada auth, by design.

## Lisensi

GPL-3.0. Untuk pemakaian pribadi dan edukasi.
