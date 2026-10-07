# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, tanpa server publik. Jalan 100% di komputermu sendiri.

## Fitur

- Pencarian judul dengan saran pencarian terakhir.
- Pilih judul, lalu pilih episode dari daftar.
- Player 16:9 dengan pilihan kualitas, subtitle multi-bahasa (atau Off), dan preferensi bahasa tersimpan.
- **Auto-Translate Subtitle Indonesia (AI 3-Tier — BYOK)**: terjemahkan subtitle English ke Indonesia secara instan menggunakan AI.
- Cahaya ambient + efek layar tabung (bisa dimatikan).
- Lanjut menonton, shortcut keyboard, riwayat lokal.
- Opsi pemutar eksternal MPV (kalau `mpv` terpasang).
- Windows: `Tatap.exe` native (WebView2), tutup jendela = backend ikut mati.

## Auto-Translate Subtitle AI (BYOK — Bring Your Own Key)

Tatap menyediakan fitur auto-translate subtitle dari track English ke Bahasa Indonesia menggunakan arsitektur **Multi-Tier Fallback**:

> [!NOTE]
> **BYOK (Bring Your Own Key)**: Tatap tidak menyediakan server LLM terpusat. Untuk mendapatkan terjemahan episode penuh secara cepat dan tanpa batas kuota harian, **kamu membawa API Key kamu sendiri** (gratis via Groq atau OpenAI).

### Tier Penerjemahan:
1. **Tier 1 (Utama & Kualitas Fansub Terbaik): AI LLM API (BYOK)**
   - Mendukung **Ollama Cloud** (`gpt-oss:20b-cloud`), **Groq** (`llama-3.3-70b-versatile`), **Google AI Studio** (`gemini-3.1-flash-lite`), dan **OpenAI** (`gpt-4o-mini`).
   - Bahasa luwes, santai (aku/kamu ala fansub), istilah gamer/anime tetap terjaga.
   - Cara pakai di web app / TUI:
     - Masukkan API key langsung di command bar / terminal Tatap:
       - `:apikey ollama_...` → otomatis preset Ollama Cloud (`gpt-oss:20b-cloud`).
       - `:apikey gsk_...` → otomatis preset Groq (`llama-3.3-70b-versatile`).
       - `:apikey AQ...` → otomatis preset Google AI Studio (`gemini-3.1-flash-lite`).
       - `:apikey sk-...` → otomatis preset OpenAI (`gpt-4o-mini`).
     - Periksa status: `:apikey`
     - Ubah model/endpoint custom: `:model <nama_model>` atau `:apiurl <url>`
     - Hapus API key: `:apikey clear`
   - *Keamanan*: Kunci API disimpan 100% lokal di database SQLite komputermu (`anime.db`) dan hanya dikirim langsung ke provider API pilihanmu.
2. **Tier 2 (Default / Fallback AI): Google GTX Web RPC**
   - Tanpa API Key (Zero-Key), tanpa batas kuota (unmetered), super cepat (~1-2 detik per episode).
   - Menggunakan preservasi tag HTML (`<p id="i">`) agar urutan kalimat stabil 100% dan bebas dari *sentence drift*.
3. **Tier 3 (Cadangan Cloud): MyMemory Translation**
   - Kuota gratis harian ~5.000 karakter per IP.
4. **Tier 4 (Safety Net): English Original**
   - Jika semua engine gagal, pemutar tetap menampilkan subtitle asli bahasa Inggris tanpa crash.

### Cara Mengaktifkan di Player:
- Klik tombol **🌐 ID** di player control bar, atau
- Pilih opsi **"Indonesian (AI)"** langsung dari dropdown subtitle (💬). Track akan otomatis diterjemahkan dan waktu cue subtitle tetap sinkron presisi.

## Mulai cepat

Linux:

```bash
chmod +x install.sh run.sh
./install.sh
./run.sh
# buka http://127.0.0.1:8767
```

Windows (portable):

1. Extract zip rilis.
2. Klik ganda `Tatap.exe` (butuh WebView2 Runtime — bawaan Windows 10/11).

## Catatan

- Berjalan lokal saja (`127.0.0.1:8767`), tanpa akun. Riwayat tersimpan di perangkatmu.
- Jangan diumbar ke internet publik.

## Batasan & Disclaimer

- **Sumber konten**: aplikasi ini melakukan scraping ke situs pihak ketiga yang saat ini dipakai sebagai sumber — katalog/pencarian ke `hianime.at`, server stream embed (megaplay/vidtube/zokoanime), metadata seasonal ke AniList GraphQL (API publik). Tatap tidak menyimpan atau mendistribusikan ulang konten tersebut; semua stream diputar langsung dari sumbernya.
- **Bisa rusak sewaktu-waktu**: kalau struktur situs sumber berubah, fitur pencarian/stream bisa berhenti bekerja sampai diperbaiki. Ini di luar kendali aplikasi.
- **Konten pihak ketiga**: ketersediaan judul, kualitas video, dan subtitle mengikuti apa yang disediakan sumber (umumnya subtitle Inggris; bahasa lain hanya kalau sumber menyediakannya).
- **Hanya pemakaian pribadi** di perangkat sendiri. Jangan dipasang di server publik atau dibagikan ulang aksesnya. Pastikan penggunaanmu mematuhi hukum yang berlaku dan ketentuan situs sumber.

## Lisensi

GPL-3.0. Untuk pemakaian pribadi dan edukasi.
