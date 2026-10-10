# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, berjalan 100% di komputermu sendiri.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L5J028GNTA)

---

## Fitur Utama

- **Katalog & Streaming Cepat**: Pencarian judul, riwayat tontonan, rekomendasi seasonal, dan pemutaran episode multi-server.
- **Player Fleksibel**: Rasio 16:9, ambient glow, mode CRT, selector resolusi, dan kontrol keyboard lengkap.
- **Pilihan Terjemahan Subtitle Indonesia**:
  - **Indonesian (AIGTX)**: Terjemahan instan (1–2 detik) dengan penyesuaian istilah anime dan dialog formal/santai.
  - **Indonesian (AI Fansub)**: Terjemahan AI bernuansa fansub santai (opsional via API key pengguna / BYOK).
  - **Indonesian (Google GTX)**: Terjemahan langsung Google Translate tanpa modifikasi.
- **Penyimpanan Lokal**: Riwayat, bookmark, dan pengaturan tersimpan di SQLite lokal (`anime.db`).
- **Pilihan Player**: Web player HTML5 bawaan atau pemutar eksternal MPV.
- **Portabel & Multi-Platform**: Tersedia executable portabel untuk Windows (WebView2) dan Linux AppImage mandiri.

---

## Subtitle Indonesia (Pilihan Mesin)

Tatap menyediakan 3 opsi terjemahan subtitle di menu dropdown player:

1. **AIGTX Translate (Default Instan)**: Langsung aktif tanpa konfigurasi API key. Menggunakan mesin cepat dengan penyesuaian istilah anime.
2. **AI Fansub (BYOK - Opsional)**: Menggunakan LLM untuk gaya bahasa yang lebih santai. Masukkan API key sendiri jika ingin menggunakan opsi ini.
3. **Google GTX**: Terjemahan standar mentah.

### Konfigurasi API Key (Hanya untuk AI Fansub):

Ketik perintah berikut di kotak pencarian / terminal Tatap:

| Perintah | Provider |
| :--- | :--- |
| `:ollama <api_key>` | [Ollama Cloud](https://ollama.com) |
| `:groq <api_key>` | [Groq](https://groq.com) |
| `:gemini <api_key>` | [Google AI Studio](https://aistudio.google.com) |
| `:openai <api_key>` | [OpenAI](https://platform.openai.com) |

Perintah bantuan:
- Cek status: `:apikey`
- Hapus API key: `:apikey clear`
- Ganti model manual: `:model <nama_model>`

---

## Cara Menjalankan

### Linux

**Opsi 1 — AppImage (Portabel):**
```bash
chmod +x Tatap-x86_64.AppImage
./Tatap-x86_64.AppImage
```

**Opsi 2 — Dari Source Repository:**
```bash
./install.sh          # Instalasi awal (sekali saja)
./manage.sh start     # Berjalan di background (buka http://127.0.0.1:8767)
./manage.sh status    # Cek status server
./manage.sh stop      # Matikan server
```

### Windows (Portable)

1. Unduh dan ekstrak **`tatap-windows-x64-portable.zip`**.
2. Klik ganda **`Tatap.exe`** (memerlukan Microsoft Edge WebView2 bawaan Windows 10/11).
3. Backend dan pemutar akan berjalan otomatis dalam jendela native tanpa perlu instalasi Python.

### Android (APK Mandiri / Standalone)

1. Unduh **`tatap-release-v2.2.0.apk`** dari halaman [GitHub Releases](https://github.com/bagusazizulamri/tatap/releases).
2. Instal di smartphone Android (Android 7.0+ / arsitektur arm64-v8a, armeabi-v7a, x86_64).
3. Buka aplikasi — Tatap menjalankan backend Python lokal otomatis di latar belakang secara mandiri (100% offline localhost tanpa butuh PC/server terpisah).
4. **Fitur & Tampilan Android**:
   - **Desain Minimalis**: Layout bersih, modern, dan bebas distorsi visual/AI-slop.
   - **Dua Tahap Subtitle Instan**: Subtitle langsung muncul pada detik pertama pemutaran tanpa jeda layar hitam.
   - **Gesture Pemutar Video**:
     - *Double-tap* kiri/kanan: Lompat -10s / +10s dengan animasi ripple ala YouTube.
     - *Double-tap* tengah: Play / Pause seketika.
     - *Swipe vertikal* kiri: Pengaturan Brightness layar dengan OSD HUD.
     - *Swipe vertikal* kanan: Pengaturan Volume audio.
     - *Swipe horizontal*: Scrubbing timeline pencarian detik cepat.
     - *HUD Buffering Cyber*: Indikator proses buffering video yang informatif dan mulus.

---

## Dukungan / Donasi

Jika Tatap bermanfaat buatmu dan ingin mentraktir kopi:

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L5J028GNTA)

---

## Disclaimer & Lisensi

- **Sumber Konten**: Tatap melakukan agregasi dari situs pihak ketiga publik (`hianime.at`, embed stream, dan AniList). Tatap tidak menyimpan atau meng-host file video apa pun.
- **Penggunaan Pribadi**: Dibuat untuk konsumsi pribadi dan edukasi di komputer lokal (`127.0.0.1`).
- **Lisensi**: GPL-3.0.
