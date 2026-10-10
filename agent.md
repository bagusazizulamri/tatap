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
* **Output:** `dist/tatap-windows-x64-portable.zip` (~26 MB)
* **Karakteristik & Isolasi Dependensi:**
  - Mengunduh Python 3.11 Embeddable x64 resmi dan mengompilasi launcher native Go `Tatap.exe`.
  - **Pencegahan Konflik Dependensi (Pydantic / Pydantic-Core):** Selalu pasang wheel murni melalui `pip install --target ... --platform win_amd64 --python-version 311 --only-binary=:all:`. Jangan pernah mengekstrak wheel dari folder cache campuran via `glob.glob()`, karena versi pustaka lama dapat menimpa versi baru dan memicu crash `SystemError: The installed pydantic-core version is incompatible with current pydantic`.

### 3. Build & Sign Android Production APK
Setiap rilis publik Android **wajib berstatus Signed APK resmi** (bukan APK debug atau unsigned):
1. **Build APK via Gradle atau CI:**
   - CI (`.github/workflows/android.yml`) otomatis mengompilasi `app-release.apk` dan `app-debug.apk`.
   - Atau build lokal: `cd android && ./gradlew assembleRelease`
2. **Penandatanganan dengan Release Keystore Resmi (`release.jks`):**
   ```bash
   apksigner sign --ks android/keystore/release.jks \
     --ks-pass pass:tatapsecret2026 \
     --ks-key-alias tatap_release \
     --key-pass pass:tatapsecret2026 \
     --out dist/android/tatap-release-v<VERSION>.apk \
     <PATH_TO_UNFINISHED_RELEASE_APK>
   ```
3. **Verifikasi Tanda Tangan:**
   ```bash
   apksigner verify --verbose --print-certs dist/android/tatap-release-v<VERSION>.apk
   ```
   Pastikan sertifikat menampilkan `CN=Tatap, OU=TatapApp, O=Tatap` dengan `APK Signature Scheme v2: true` dan `v3: true`.

---

## 5. Protokol Git & GitHub Release

### Konvensi Commit
Gunakan format **Conventional Commits**:
- `feat(...)`: Fitur baru (misal: gesture, layout responsif, subtitle provider).
- `fix(...)`: Perbaikan bug (sertakan referensi isu jika ada, misal: `fix(player): retain subtitles in fullscreen mode (closes #1)`).
- `docs(...)`: Pembaruan dokumentasi (README, agent.md).
- `build(...)` / `chore(...)`: Perubahan build system, CI workflow, atau packaging.

### Standar Aset Release Publik (Protokol "Tarik APK Mentah")
Halaman rilis publik GitHub **hanya boleh menyajikan 3 berkas resmi yang bersih dan terverifikasi**:
1. 📱 **`tatap-release-v<VERSION>.apk`** (Official Signed APK)
2. 🪟 **`tatap-windows-x64-portable.zip`** (Windows Portable)
3. 🐧 **`Tatap-x86_64.AppImage`** (Linux AppImage)

**Langkah Penyelarasan Rilis:**
1. Update git tag:
   ```bash
   git tag -a v<VERSION> -m "Release v<VERSION>"
   git push origin v<VERSION>
   ```
2. Upload signed APK dan paket binary portable:
   ```bash
   gh release upload v<VERSION> \
     dist/android/tatap-release-v<VERSION>.apk \
     dist/tatap-windows-x64-portable.zip \
     dist/Tatap-x86_64.AppImage \
     --clobber
   ```
3. **Tarik & Hapus APK Mentah Bawaan CI:**
   Karena CI mengunggah nama mentah secara otomatis, segera hapus dari rilis publik agar pengguna tidak bingung:
   ```bash
   gh release delete-asset v<VERSION> app-release.apk -y
   gh release delete-asset v<VERSION> app-debug.apk -y
   ```
4. **Perbarui Release Notes:**
   Tulis catatan rilis berbahasa Indonesia yang terstruktur rapi, mencantumkan perbaikan bug, penambahan fitur, dan panduan download untuk ketiga platform.

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

## 7. Standar Pemutar Video Android & Katalog Metadata

### 1. Akurasi Gesture Swipe & Audio
- **Gesture Volume Tanpa Lag:** Pada `PlayerActivity.java`, gunakan **continuous float accumulator** (`currentVolumeFraction`) yang diinisialisasi dari rasio `currentVolume / maxVolume` pada saat `ACTION_DOWN`. Hindari *integer truncation* dari perhitungan jarak per-event (`(int)(distanceY * maxVol)`) yang menyebabkan swipe pelan/halus macet atau "nyangkut" di perangkat modern (Android 14, 15, dan 16).
- **Brightness Float Accumulator:** Nilai brightness layar disimpan dalam float `0.01f - 1.0f` dan diperbarui ke `WindowManager.LayoutParams.screenBrightness`.

### 2. Standar Tipografi & Penempatan Subtitle Mobile
- **Posisi Default Ergonomis:** Margin bawah default subtitle Android disetel ke `22dp` (bukan 50dp+) agar tidak menutupi ekspresi wajah karakter atau adegan sentral dalam rasio lanskap layar HP/tablet.
- **Kustomisasi Subtitle (`Style Dialog`):** Sediakan menu pengaturan subtitle dengan opsi kustomisasi:
  - Posisi: *Bawah (22dp)*, *Sangat Bawah (10dp)*, *Sedang (40dp)*, *Tinggi (58dp)*.
  - Background Opacity: *Transparan Sedang (30%)*, *Tipis (15%)*, *Gelap (70%)*, atau *Tanpa Kotak (Text Shadow murni)*.
  - Ukuran Teks: *14sp*, *16sp*, *19sp*, dan *22sp*.
  - Semua preferensi disimpan secara persisten di `SharedPreferences` (`tatap_player_prefs`).

### 3. Validasi Pencocokan Katalog Anime (AniList ke HiAnime)
- **Konsistensi Musim (Season Consistency):** Skrip pencocokan di `backend/main.py` (`_match_slug_one`) **wajib memverifikasi nomor musim** (`_extract_season_num`) dan token kemiripan judul (`_is_title_match`).
- **Pencegahan Fallback Keliru:** Dilarang menggunakan fallback buta ke hasil pertama (`res[0]`) ketika nama tidak cocok. Fallback keliru akan mencemari database cache permanen (`slug_map`), membuat anime Season baru/on-going tertukar dengan Season 1 atau judul yang sama sekali berbeda.
- **Tab On-going / Airing:** Tab anime yang sedang tayang harus selalu mengueri data status penayangan aktif langsung dari katalog stream (`/api/seasonal?which=airing`).

### 4. Kompatibilitas Packaging & Instalasi Android (16KB Page Alignment & Android 15/16)
- **Ekstraksi Pustaka Native:** Wajib menyetel `packaging.jniLibs.useLegacyPackaging = true` di `build.gradle` dan `android:extractNativeLibs="true"` di `AndroidManifest.xml`.
- **Akar Masalah Kegagalan Instal:** Pada Android 15, Android 16, dan perangkat 64-bit modern (seperti seri Infinix Note 40 / MediaTek / Transsion XOS), pustaka native uncompressed yang tidak ter-align pada batas 16KB akan langsung ditolak oleh PackageInstaller OS (`INSTALL_FAILED_INVALID_APK`). Dengan `useLegacyPackaging = true`, file `.so` dikompresi di APK dan diekstrak secara otomatis ke penyimpanan privat saat dipasang, menjamin 100% kompatibilitas dan menghemat ukuran unduhan APK dari ~54MB menjadi ~35MB.

---

## 8. Prinsip Rekayasa Agen AI (Agent Guardrails)

- **Dokumentasi & Integritas Kode:** Jangan pernah menghapus komentar atau docstring yang ada kecuali diminta secara eksplisit atau sudah tidak relevan karena perubahan kode.
- **Verifikasi Sebelum Klaim Sukses:** Selalu jalankan uji sintaksis (`node --check`, linting, build test) sebelum mendeklarasikan tugas selesai.
- **Transparansi Kerja:** Laporkan langkah kerja secara ringkas, jelas, dan sertakan tautan ke file atau artefak terkait.
