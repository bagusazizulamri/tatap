# Tatap

> **Nonton anime santai tanpa ribet.**  
> Pemutar anime mandiri multi-platform (Web Desktop, Windows, Linux, dan Android) — ringan, tanpa iklan mengganggu, tanpa perlu daftar akun, dan privasi tetap di perangkatmu sendiri.

[![Release](https://img.shields.io/github/v/release/bagusazizulamri/tatap?style=flat-square&color=00f0ff)](https://github.com/bagusazizulamri/tatap/releases)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=flat-square)](LICENSE)
[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L5J028GNTA)

---

## Kenapa Tatap?

Sering merasa jengkel saat ingin menonton anime di browser karena:
- Terlalu banyak pop-up iklan mencurigakan dan link redirect?
- Tautan video sering diblokir oleh sensor internet atau gangguan ISP?
- Terjemahan subtitle otomatis terasa kaku, aneh, atau tidak nyambung?
- Aplikasi streaming yang ada terasa berat dan menuntut registrasi akun?

**Tatap** dibuat untuk menyelesaikan masalah-masalah di atas secara sederhana dan bersahabat. Aplikasi ini bertindak sebagai pemutar lokal mandiri (*standalone localhost backend*): kamu mendapatkan pengalaman menonton yang bersih, estetik, dan lancar langsung dari perangkatmu.

---

## Fitur Utama

- 🚫 **Bersih Tanpa Iklan & Tanpa Akun**: Tidak ada banner sponsor, tidak ada pop-up, dan tidak perlu mendaftar atau memasukkan data pribadi apa pun.
- 📺 **Player Estetik & Nyaman di Mata**:
  - **Ambient Stage Light**: Efek pendaran cahaya dinamis di sekitar video yang berubah warna mengikuti suasana adegan yang sedang diputar.
  - **Mode Retro CRT**: Filter visual opsional dengan efek scanline untuk nuansa nostalgia layar tabung.
  - **Rasio & Resolusi Fleksibel**: Pilihan resolusi otomatis sesuai kecepatan internet dan rasio 16:9 yang pas.
- 🇮🇩 **Pilihan Subtitle Bahasa Indonesia**:
  - **Subtitle Resmi / Bawaan**: Langsung aktif jika penyedia stream menyediakan takarir resmi (Indonesia / Inggris).
  - **AIGTX (Default Siap Pakai)**: Terjemahan mesin cepat (1–2 detik) yang sudah dilengkapi kamus 500+ istilah anime umum (shounen, isekai, ninja, slice-of-life) agar dialog terdengar lebih alami dan tidak kaku.
  - **AI Fansub (Opsional / BYOK)**: Ingin gaya bahasa yang lebih luwes ala fansub manual? Kamu bisa menghubungkan API key AI milikmu sendiri (Gemini, Groq, OpenAI, Ollama).
  - **Kustomisasi Tampilan**: Ukuran teks, posisi vertikal, dan transparansi background subtitle dapat diatur agar tidak menutupi visual penting.
- ⚡ **Bypass Pemblokiran Terintegrasi (DPI-Bypass)**: Dilengkapi modul soket TLS desync otomatis, sehingga stream video tetap lancar diakses tanpa perlu menyalakan VPN tambahan.
- 📂 **Penyimpanan Lokal (Offline-First Privacy)**: Riwayat tontonan (*watch history*), penanda (*bookmark*), dan pengaturan tersimpan aman di database SQLite lokal perangkatmu (`anime.db`).

---

## Pilihan Download & Cara Menjalankan

Pilih platform yang paling cocok untuk perangkatmu:

### 📱 Android (Smartphone & Tablet)

Aplikasi Android Tatap dibangun dengan UI native penuh dan pemutar **AndroidX Media3 ExoPlayer**, lengkap dengan mesin gesture sentuh modern:

1. Unduh berkas **`tatap-release-v2.2.1.apk`** dari halaman [GitHub Releases](https://github.com/bagusazizulamri/tatap/releases).
2. Pasang di smartphone (kompatibel dengan Android 7.0 hingga Android 16 terbaru, ukuran hemat ~35 MB).
3. Buka aplikasi dan langsung nikmati:
   - *Double-tap* sisi kiri/kanan untuk mundur/maju 10 detik.
   - *Swipe vertikal* kiri untuk mengatur kecerahan layar.
   - *Swipe vertikal* kanan untuk mengatur volume suara.
   - Dialog pengaturan subtitle langsung dari tombol kontrol player.

---

### 🪟 Windows (Portable)

Tidak perlu menginstal Python atau mengatur konfigurasi yang rumit:

1. Unduh **`tatap-windows-x64-portable.zip`** dari halaman [GitHub Releases](https://github.com/bagusazizulamri/tatap/releases).
2. Ekstrak file zip ke folder mana saja.
3. Klik ganda **`Tatap.exe`** untuk langsung membuka pemutar (menggunakan runtime Microsoft Edge WebView2 bawaan Windows 10/11).

---

### 🐧 Linux

**Opsi 1 — AppImage (Tinggal Jalankan):**
```bash
# 1. Unduh berkas Tatap-x86_64.AppImage dari halaman Releases
# 2. Beri izin eksekusi:
chmod +x Tatap-x86_64.AppImage

# 3. Jalankan:
./Tatap-x86_64.AppImage
```

**Opsi 2 — Dari Source Repository (Bagi yang Suka Oprek):**
```bash
git clone https://github.com/bagusazizulamri/tatap.git
cd tatap

./install.sh          # Setup venv & dependensi (hanya sekali)
./manage.sh start     # Menjalankan server di background
```
Buka browser dan akses **`http://127.0.0.1:8767`**.  
Untuk menghentikan: `./manage.sh stop`.

---

## Pintasan Keyboard (Desktop Player)

Nonton lebih praktis dengan kendali keyboard:

| Tombol | Aksi |
| :--- | :--- |
| `Spasi` / `K` | Putar / Jeda video (Play / Pause) |
| `F` | Masuk / Keluar Layar Penuh (*Ambient Stage*) |
| `←` / `→` | Mundur / Maju 5 detik |
| `J` / `L` | Mundur / Maju 10 detik |
| `↑` / `↓` | Tambah / Kurangi volume suara |
| `M` | Matikan / Nyalakan suara (*Mute*) |
| `C` | Aktifkan / Matikan filter visual CRT |
| `Esc` | Keluar dari mode layar penuh |

---

## Konfigurasi AI Fansub (Opsional)

Jika ingin memakai terjemahan berbasis model bahasa (LLM) dengan API key pribadi, kamu cukup mengetikkan perintah berikut pada kolom pencarian / terminal Tatap:

| Perintah | Layanan AI |
| :--- | :--- |
| `:gemini <api_key>` | [Google AI Studio (Gemini)](https://aistudio.google.com) |
| `:groq <api_key>` | [Groq Cloud (Llama/Mixtral Cepat)](https://groq.com) |
| `:openai <api_key>` | [OpenAI (GPT-4o mini)](https://platform.openai.com) |
| `:ollama <api_key>` | [Ollama Cloud / Local](https://ollama.com) |

Perintah utilitas:
- Cek status kunci aktif: `:apikey`
- Hapus kunci API: `:apikey clear`
- Pilih model tertentu secara manual: `:model <nama_model>`

> **Catatan:** Fitur ini sepenuhnya opsional. Tanpa API key pun, subtitle **AIGTX** bawaan sudah langsung bekerja secara otomatis dan gratis.

---

## Kejujuran & Batasan Teknis (Disclaimer)

- **Konektivitas Internet:** Tatap adalah pemutar mandiri di sisi lokal, tetapi **bukan aplikasi arsip offline 100%**. Kamu tetap membutuhkan koneksi internet untuk memuat daftar anime, poster, dan mengalirkan (*streaming*) video dari sumber publik.
- **Ketersediaan Sumber:** Kestabilan dan kecepatan video bergantung pada penyedia sumber publik pihak ketiga dan kondisi ISP pengguna.
- **Penyimpanan Berkas:** Tatap tidak meng-host, menampung, atau memiliki server penyimpan video sendiri. Aplikasi ini murni berperan sebagai alat agregator dan pemutar konten publik.
- **Lisensi:** Proyek ini dilisensikan di bawah [GPL-3.0](LICENSE) untuk kebutuhan personal dan edukasi.

---

## Dukungan & Apresiasi

Jika Tatap membuat pengalaman nontonmu lebih nyaman dan ingin mentraktir secangkir kopi:

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L5J028GNTA)
