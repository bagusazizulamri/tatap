# AGENT.md — Tatap Engineering & Collaboration Workflow

Panduan standar ini mematenkan arsitektur, workflow engineering, tata kelola rilis, dan protokol penanganan isu untuk agen AI dan kontributor pada proyek **Tatap**.

---

## 1. Identitas & Filosofi Proyek

**Tatap** adalah pemutar dan agregator anime multiplatform (Web Desktop, Windows Portable, Linux AppImage, dan Native Android) dengan fokus pada:
- **Zero-Bloat & Standalone Runtime:** Berjalan tanpa dependensi eksternal yang rumit (menggunakan embedded/standalone runtime di semua platform).
- **Resilient Networking:** Scraping sumber anime dengan proteksi TLS desync DPI-bypass untuk menjaga konektivitas stabil.
- **Smart Subtitle Fallback:** Sistem subtitle multi-tier (AIGTX Smart Lexicon, AI Fansub BYOK LLM, Google Translate GTX, dan Native WEBVTT sync).
- **Akurasi Klaim Teknis:** Jangan pernah mengklaim "100% Offline" karena aplikasi melakukan scraping stream online. Gunakan istilah yang akurat seperti *"Standalone Localhost Backend"* atau *"Aplikasi Mandiri Tanpa Server Publik"*.

---

## 2. Peta Arsitektur Codebase

```
tatap/
├── backend/                  # Server FastAPI & API Scraping
│   ├── main.py               # Entry point FastAPI, routing, API subtitle & stream
│   ├── config.py             # Konfigurasi port, path DB, dan environment
│   ├── database/             # SQLite database handler (history, bookmark, settings)
│   └── api/                  # Modul scraper: anilist, hianime, otakudesu, translate, desync
├── frontend/                 # Web UI (Zero-build vanilla JS & CSS)
│   ├── index.html            # Single-page UI structure & modals
│   ├── js/                   # app.js (state & playback), api.js, term.js, hls.min.js
│   └── css/                  # style.css (Dark cyber theme, responsive grids, fullscreen)
├── android/                  # Native Android App
│   ├── app/src/main/java/    # UI Native Java: MainActivity, DetailActivity, PlayerActivity (ExoPlayer)
│   ├── app/src/main/python/  # Backend FastAPI embedded via Chaquopy
│   └── app/build.gradle      # Konfigurasi build & signingConfigs release keystore
├── tools/                    # Automated Desktop Packaging Tools
│   ├── build_linux_appimage.py      # Builder AppImage (Python standalone + appimagetool)
│   └── build_windows_portable.py    # Builder Portable Windows (Python embed + Go launcher)
├── launcher/                 # Source Go untuk launcher native Windows (Tatap.exe)
├── dist/                     # Direktori output build binary rilis
└── agent.md                  # Standard Operating Procedure (file ini)
```

---

## 3. Standar UI/UX Pemutar Video & Subtitle

### Subtitle Dual-Layer Rendering
Player Tatap menggunakan pendekatan **Dual-Layer** untuk kompatibilitas maksimal:
1. **App-Level Custom Overlay (`#pm-subs-overlay`):** Digunakan saat pemutaran normal atau saat container `.ambient-stage` masuk mode fullscreen. Memungkinkan styling kustom (ukuran S/M/L, font shadow tebal, background translucent) dan live update translation.
2. **Native TextTrack Synchronization (`VTTCue`):** Subtitle yang diparsing wajib disinkronkan ke elemen `<video>` via `HTMLVideoElement.addTextTrack` atau `<track>`. Saat pengguna masuk fullscreen melalui tombol kontrol bawaan browser pada elemen `<video>`, browser mempromosikan elemen video ke top layer; native track otomatis aktif (`showing`) dan dirender melalui styling CSS `video::cue`.

### Fullscreen Promotion Strategy
- **Container Level:** Shortcut `f` / `F`, double-click pada area video, atau tombol **`⛶ FULL`** memicu `requestFullscreen()` pada `.ambient-stage`, bukan langsung pada elemen `<video>`.
- **Interception:** Panggilan native `v.requestFullscreen()` di-intercept untuk memprioritaskan fullscreen pada container `.ambient-stage`.
- **Keyboard Shortcut Safety:** Tombol `Escape` saat berada dalam mode fullscreen hanya keluar dari fullscreen tanpa menutup modal pemutar.

---

## 4. Alur Kerja Build & Packaging (Release Pipeline)

Setiap rilis versi stabil mengikuti tahapan berikut:

### 1. Build Linux AppImage
```bash
python3 tools/build_linux_appimage.py
```
* **Output:** `dist/Tatap-x86_64.AppImage` (~58 MB)
* **Karakteristik:** Membungkus runtime CPython 3.11 standalone, dependensi pip, backend, frontend, icon, dan desktop launcher mandiri yang dapat langsung dijalankan (`chmod +x`).

### 2. Build Windows Portable
```bash
python3 tools/build_windows_portable.py
```
* **Output:** `dist/tatap-windows-x64-portable.zip` (~23 MB)
* **Karakteristik:** Membungkus Python 3.11 Embeddable x64, wheel packages terisolasi, launcher native Go `Tatap.exe` tanpa dependensi runtime eksternal.

### 3. Build & Sign Android Production APK
```bash
cd android && ./gradlew assembleRelease
```
* **Output:** `android/app/build/outputs/apk/release/app-release.apk` -> disalin ke `dist/android/tatap-release-v<VERSION>.apk`
* **Verifikasi Tanda Tangan (Keystore):**
```bash
apksigner verify --verbose dist/android/tatap-release-v<VERSION>.apk
```
Pastikan `Verified using v1 scheme: true` dan `Verified using v2 scheme: true`.

---

## 5. Protokol Git & GitHub Release

### Konvensi Commit
Gunakan format **Conventional Commits**:
- `feat(...)`: Fitur baru (misal: gesture, layout responsif, subtitle provider).
- `fix(...)`: Perbaikan bug (sertakan referensi isu jika ada, misal: `fix(player): retain subtitles in fullscreen mode (closes #1)`).
- `docs(...)`: Pembaruan dokumentasi (README, agent.md).
- `build(...)`: Perubahan build system atau packaging (Android gradle, AppImage, dll.).

### Pembuatan & Pembaruan Release
1. Update git tag:
   ```bash
   git tag -fa v<VERSION> -m "Release v<VERSION>: <Summary>"
   git push origin v<VERSION> --force
   ```
2. Upload aset rilis (timpa aset jika memperbarui rilis yang sama):
   ```bash
   gh release upload v<VERSION> \
     dist/Tatap-x86_64.AppImage \
     dist/tatap-windows-x64-portable.zip \
     dist/android/tatap-release-v<VERSION>.apk \
     --clobber
   ```
3. Perbarui Release Notes:
   Gunakan bahasa Indonesia yang jelas, ramah pengguna, dan terstruktur rapi memuat poin-poin fitur baru, perbaikan bug, dan panduan unduh.

---

## 6. Protokol Triage & Feedback GitHub Issues

Saat menangani issue dari pengguna/komunitas di GitHub:
1. **Inspeksi Isu:**
   * Gunakan REST API via `gh api repos/:owner/:repo/issues/:id` untuk menghindari kegagalan GraphQL pada versi CLI lama.
   * Pahami sistem operasi, browser/perangkat, dan bukti tangkapan layar dari pelapor.
2. **Diagnosis & Solusi:**
   * Cari akar penyebab di kode dasar (bukan sekadar penambal sementara).
   * Verifikasi solusi di lingkungan lokal sebelum melakukan commit.
3. **Bahasa Komunikasi:**
   * **Commit & Internal Repo:** Bahasa Inggris standar industri (Conventional Commits).
   * **Balasan / Feedback ke Pelapor di GitHub:** **Wajib menggunakan Bahasa Inggris** yang sopan, jelas, ramah, dan profesional.
   * Format balasan:
     - Ucapan terima kasih atas laporan.
     - Penjelasan singkat akar masalah (*Root Cause*).
     - Rincian perbaikan teknis yang dilakukan (*Fix Implemented*).
     - Informasi versi rilis / commit tempat perbaikan tersedia beserta tautan langsung.
     - Undangan untuk memverifikasi atau memberikan feedback balik.

---

## 7. Prinsip Rekayasa Agen AI (Agent Guardrails)

- **Dokumentasi & Integritas Kode:** Jangan pernah menghapus komentar atau docstring yang ada kecuali diminta secara eksplisit atau sudah tidak relevan karena perubahan kode.
- **Verifikasi Sebelum Klaim Sukses:** Selalu jalankan uji sintaksis (`node --check`, linting, build test) sebelum mendeklarasikan tugas selesai.
- **Transparansi Kerja:** Laporkan langkah kerja secara ringkas, jelas, dan sertakan tautan ke file atau artefak terkait.
