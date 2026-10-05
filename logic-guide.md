# logic-guide.md — Tatap

Panduan logic seragam untuk semua AI agent yang menyentuh repo ini.
Baca ini SEBELUM mengubah kode. Jangan improvisasi yang melanggar aturan di bawah.

## 1. Techstack — JANGAN diubah

| Lapis | Teknologi | Aturan |
|---|---|---|
| Backend | FastAPI + uvicorn | Python. Tidak menambah framework. |
| DB | SQLite via aiosqlite | Tabel: search_cache, episode_cache, watch_history, settings, browse_cache. |
| Scraper | curl_cffi (impersonate chrome124) + httpx | Sumber tunggal: hianime.at (HI_BASE). |
| Player | hls.js (vendor, lokal) | Tanpa CDN. |
| Frontend | HTML + CSS + JS vanilla, TANPA build step | ES5-ish (`var`, `function`). Tidak ada bundler, tidak ada npm, tidak ada TypeScript, tidak ada framework. |

Kalau butuh fitur baru: pakai yang sudah ada di requirements.txt / vendor. Jangan tambah dependensi tanpa izin user.

## 2. Kontrak API — backend tidak diubah untuk perombakan UI

Semua response: `{success: true, data: {...}}` atau `{success: false, error: str}`.
Status HTTP selalu 200 (lihat `ok()`/`fail()` di main.py).

| Endpoint | Data balik | Catatan |
|---|---|---|
| `GET /api/search?q=` | `{results:[{id,title}], cached}` | HANYA id+title. Tidak ada poster. |
| `GET /api/seasonal?which=now\|prev&page=1` | `{season, year, items:[...], total_pages=1}` | Sumber: AniList GraphQL. Judul dicocokkan ke slug hianime via search; item tanpa match punya `id=""` & `matched:false`. Pagination dikunci 1 halaman (AniList over-reports). |
| `GET /api/upcoming-episodes?days=7` | `{items:[{id,title,episode,airing_at,airing_at_iso,weekday,date,time,poster}], days, total, current_season, previous_season, current_year, cached}` | Episode yang rilis dalam N hari ke depan (default 7, max 30). Filter musim akurat: hanya anime dengan `seasonYear=current` & `season=current OR previous` (case-insensitive), atau `season=null` (ongoing lama). Cache 1 jam. |
| `GET /api/catalog?page=` | `{items:[Anime], page, total_pages, cached}` | |
| `GET /api/browse?{filter}&page=` | `{items:[Anime], page, total_pages, cached}` | |
| `GET /api/season-now?page=` | sama browse + `season` | |
| `GET /api/still-airing?page=` | sama browse + `season` | |
| `GET /api/anime/{slug}/episodes` | `{slug, episodes:[{ep,ep_id}], total}` | |
| `GET /api/stream/resolve?slug=&ep=&mode=&q=` | `{variants:[{q,url}], picked, sub, referer, server, subtitles:[{label,lang,url,default}], cached}` | `subtitles` = seluruh track subtitle hasil scrape (normalisasi). `sub` = URL track default (backward compat). |
| `GET /api/player/video?url=&referer=` | stream | proxy segmen/playlist |
| `GET /api/player/sub?url=&referer=` | VTT | |
| `POST /api/play-mpv` | `{cmd, picked, subs_attached}` | spawn mpv lokal. Body opsional `sub_url` (track yang sedang aktif di UI). Backend attach SELURUH `subtitles[]` via multi-arg `--sub-file=` (dedupe by URL). `subs_attached` = jumlah track yang berhasil di-download. |
| `GET/POST/DELETE /api/history` | list history | |
| `GET /api/filters` | `FILTERS` dari hianime.py | Otoritatif untuk opsi filter. |
| `GET/POST /api/settings` | `{quality,mode,player,sub_lang}` | `sub_lang` (default "English") = preferensi bahasa subtitle user yang persistent. Disimpan saat user pilih track di dropdown; dipakai frontend untuk auto-select track di episode berikutnya. |

Objek `Anime` (dari browse): `{id, title, poster, sub, dub, eps, type, duration, synopsis}`.
`id` selalu = slug. `openTitle(id, title)` memakai slug ini.
`/api/search` sengaja kembalikan `{id, title}` saja (tanpa poster) — UI render baris teks untuk hasil search.

### Catatan scraper (per Oktober 2026)
- hianime sudah discontinue halaman per-season (`/browse?season=fall` dll) — JANGAN pakai endpoint `/api/browse` atau `/api/catalog` untuk daftar seasonal. Gunakan `/api/seasonal` (AniList).
- AniList `/seasons/{year}/{value}` sering kosong untuk season lampau. Lebih aman via GraphQL `Page(season:..., seasonYear:...)` di endpoint kita.
- AniList `PageInfo` over-reports untuk query season-filter (contoh Fall 2026 mengembalikan `total:5000, lastPage:200`). Endpoint `/api/seasonal` memaksa `total_pages=1`.
- Slug lookup ke hianime via `hianime_search(title, 5)`; hasil pertama dipakai kalau tidak ada exact match. Cache disimpan di tabel `slug_map` TTL 7 hari.
- AniList `airingSchedules` harus via `Page.airingSchedules(...)` (bukan `AiringSchedule` sebagai satu item). `Page` adalah connection, `AiringSchedule` adalah satu entity.

### Multi-subtitle (plan: Opsi Multi-Subtitle Tatap)
- Backend ekstrak & normalisasi seluruh track subtitle lewat `_normalize_subtitles()` di `backend/api/hianime.py`. Filter track non-subtitle (`kind != subtitles/captions`), resolve URL relatif terhadap `referer`, expand label kode bahasa 2-char (`ja` → `Japanese`), auto-mark `default:true` kalau tak ada.
- DB schema: kolom `episode_cache.subtitles TEXT DEFAULT '[]'` (JSON array). Migrasi idempotent — `ALTER TABLE` di `init_db()` di-try/except agar DB lama auto-upgrade tanpa error.
- Frontend (`#pm-subs-wrap` di `.player-foot`, sebelah `pm-variants`): dropdown `💬 SUB: [English ▾]` berisi opsi `Off` + daftar bahasa. Pilih track → ganti `<track>` di `<video>` secara live (tanpa reload), simpan label ke `sub_lang` di `/api/settings`.
- Episode berikutnya: `cur.subLang` dibaca dari `/api/settings` di `init()`; `pickSubtitleUrl()` cocokkan label/partial/code → fallback ke `default:true`.
- MPV: `POST /api/play-mpv` accept `sub_url` (track aktif). Backend tetap attach SELURUH `subtitles[]` (multi-arg `--sub-file`) supaya user bisa cycle via tombol `j` di MPV. Dedupe by URL agar `sub` default tidak dobel kalau sudah ada di `subtitles[]`.

### Smart-fallback server (per Oktober 2026)
- Tier urutan: `megaplay` (HD-1, Vidstream-2) → `vidtube.site` (VidPlay-1, juga pakai `window.__P`) → `zokoanime.video` (pakai CDN `hls.dramahot.top`).
- `hls.dramahot.top` awalnya ditandai RST dari region kita (disimpan di `_DEAD_HOSTS` + negative-cache 1 jam via `_mark_dead()`). Per Oct 2026 host sudah pulih (TLS handshake & HTTP 404 sukses) sehingga nama host dihapus dari `_DEAD_HOSTS`; kalau RST lagi nanti, `_mark_dead()` akan menambahkannya ke negative cache dan smart-fallback otomatis skip server ZokoAnime.
- Tiap success path panggil `_probe_master()` (HEAD/GET kecil) sebelum return. Kalau probe gagal → raise → caller smart-fallback ke server berikutnya.
- Megaplay sukses pakai CDN `fetch.nexabloom.top` + `fn5an.wintergrove.space` — routeable.
- Proxy endpoint `/api/player/video` tidak lagi memblokir upstream `dramahot.top` langsung; kalau upstream kembali RST, error disurfacing sebagai HTTP 502 dari httpx dan HLS.js deteksi `networkError`/`fragLoadError` untuk fallback.

## 3. Model state frontend

```
Tui state (halaman utama / terminal):
  view      : "cari" | "musim" | "lanjutan" | "katalog"
  items     : array hasil aktif
  sel       : index item terpilih (-1 = tak ada)
  page,total: paging
  filter    : objek filter katalog
  recents   : localStorage "tatap_recent"  (saran pencarian)
  cmdHist   : localStorage "tatap_hist"    (riwayat command)

Playback state:
  cur = {slug,title,ep,mode,quality,res,eps,watched}
```

## 4. Dua mode render hasil

| View | Sumber data | Bentuk | Alasan |
|---|---|---|---|
| cari | `/api/search` | baris teks (`id`+`title`) | backend tak kirim poster |
| musim, lanjutan, katalog | `/api/browse*` | poster grid | data lengkap |

JANGAN paksa poster ke hasil search tanpa mengubah backend. JANGAN render baris teks untuk browse (kehilangan poster).

## 5. Precedence keyboard — SATU handler global

Urutan wajib, dari atas:
```
1. Ctrl+C         → batalkan isi prompt, tetap di view
2. modal terbuka? → TERUSKAN ke handler modal. JANGAN sentuh state Tui.
3. prompt fokus   → Enter submit; Esc blur; Tab cycle view;
                    ↑/↓ riwayat command HANYA bila items kosong
4. player aktif   → Space/n/p/m/←/→ milik player
5. default        → ↑/↓ pilih; Enter buka; Tab cycle view;
                    [/] paging; Esc reset; ketik huruf → fokus prompt
```
Larangan eksplisit:
- Menekan `n` di halaman utama TIDAK boleh memicu `stepEp`. (Bug lama.)
- `/` saat player terbuka TIDAK boleh fokus ke input tersembunyi. (Bug lama.)
- `Esc` di prompt: bersihkan prompt dulu, blur kedua kali.

## 6. Grammar command prompt

Prefix `:` = command. Tanpa prefix = search.
```
:cari <judul>        :musim        :lanjutan       :katalog
:filter key=value    :filter reset :reset          :status
:crt on|off|toggle   :ambient on|off|toggle
:riwayat             :bantuan|:help|:?              :q|:clear
```
Command tak dikenal → cetak baris error log, JANGAN crash.
Command tanpa argumen yang butuh argumen → cetak usage.

## 7. Kontrak ID (modal & player) — WAJIB dipertahankan

Elemen berikut tidak boleh di-rename / dihapus. app.js meng-query dengan ID ini:
```
title-modal, tm-eyebrow, tm-title, tm-sub, tm-count, tm-eps, tm-close,
ep-filter, mode-seg, quality-seg
player-modal, pm-title, pm-meta, pm-close, pm-mpv, pm-prev, pm-next,
pm-variants, pm-subs-wrap, pm-subs, pm-spinner, pm-status, vid, ambient,
ambient-fallback, .ambient-stage, .player-shell, .player-foot, .player-hint
```
Modal hanya boleh di-restyle (font/border/radius). Struktur & behavior playback tidak diubah.

## 8. Persistensi localStorage
```
tatap_crt     "on"|"off"          efek CRT
tatap_ambient "on"|"off"          ambient light
tatap_recent  JSON array string   6 pencarian terakhir
tatap_hist    JSON array string   riwayat command (max 50)
```

## 9. Aturan kode frontend
- ES5: `var`, `function`, no arrow, no const/let, no optional chaining.
- Tanpa komentar kecuali diminta.
- Tanpa emoji di kode/UI kecuali user minta.
- Escape semua teks dinamis sebelum masuk innerHTML (ada `esc()`).
- Satu handler keydown global; jangan pasang banyak listener terpisah untuk hal sama.

## 9a. Aturan responsivitas
- Pakai variabel CSS di `:root` (`--pad-x`, `--fs-base`, `--status-h`) bukan angka magic.
- Pakai `clamp()` untuk font/spacing yang fluid. Hardcode pixel hanya di value prop (radius, border).
- Breakpoint: 480 / 640 / 900 / 1280 / 1600. Tambahkan hanya jika kebutuhan jelas.
- Player fullscreen di mobile (<480px): `width/height: 100vh`, padding aman `env(safe-area-inset-*)`.
- Sticky `.prompt` & `.sticky `.statusbar` saling referensi via `bottom: var(--status-h)` (statusbar set nilai, prompt pakai). JANGUN hardcode angka seperti `bottom: 38px`.
- `prefers-reduced-motion: reduce` wajib dihormati untuk animasi (caret blink, ring spinner).
- Selalu uji di viewport 360×640 (ponsel kecil), 768×1024 (tablet), 1280×800 (laptop), 1920×1080 (desktop), 2560×1080 (ultra-wide).

## 10. Perintah verifikasi
```bash
./manage.sh start      # jalan
./manage.sh status
./manage.sh logs
./manage.sh stop
```
Smoke: `curl -s localhost:8767/api/health`
Tidak ada test suite. Verifikasi = manual checklist di plan.

## 11. Definisi "selesai" untuk perombakan UI
- Halaman utama = terminal UI (command prompt, list/grid, statusbar).
- Modal title & player = masih modal lama, di-restyle ringan.
- Semua command di §6 jalan.
- Precedence §5 terpenuhi (uji `n` di home, `/` di player).
- Backend tidak berubah.