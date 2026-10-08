# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, berjalan 100% di komputermu sendiri.

---

## Fitur Utama

- **Katalog & Streaming Cepat**: Pencarian judul, riwayat tontonan, rekomendasi seasonal, dan pemutaran episode multi-server.
- **Player Fleksibel**: Rasio 16:9, ambient glow, mode CRT/layar tabung, selector resolusi, dan kontrol keyboard lengkap.
- **Auto-Translate Subtitle Indonesia (AI Fansub)**: Menerjemahkan subtitle English ke Bahasa Indonesia dengan gaya percakapan fansub santai (*aku/kamu*, *nggak*, *udah*, *aja*) secara instan.
- **100% Penyimpanan Lokal**: Riwayat, bookmark, dan pengaturan tersimpan di SQLite lokal (`anime.db`).
- **Pilihan Player**: Web player HTML5 bawaan atau pemutar eksternal MPV.

---

## Petunjuk Subtitle AI (BYOK — Ollama)

Tatap menggunakan konsep **BYOK (Bring Your Own Key)** agar kamu bisa menikmati terjemahan AI berkualitas fansub secara gratis dan tanpa batasan.

### Cara Memasang API Key Ollama:

1. Dapatkan API key gratis dari [Ollama Cloud](https://ollama.com).
2. Buka aplikasi Tatap di browser ([http://127.0.0.1:8767](http://127.0.0.1:8767)).
3. Ketik perintah berikut langsung di kotak pencarian / terminal Tatap:
   ```text
   :ollama <api_key_kamu>
   ```
   *(Contoh: `:ollama afd1045d...`)*

Tatap akan otomatis mengatur:
- **Provider**: Ollama Cloud (`https://ollama.com/v1`)
- **Model**: `gpt-oss:20b` *(dengan cadangan otomatis `gpt-oss:120b` jika antrean penuh)*

### Perintah Bantuan Terminal:
- Cek status konfigurasi: `:apikey`
- Hapus API key: `:apikey clear`
- Ganti model manual: `:model gpt-oss:20b`

> [!TIP]
> **Tanpa API Key?** Jika belum memasukkan API key, Tatap tetap menyediakan fallback otomatis menggunakan **Google GTX (Zero-Key)** sehingga subtitle Indonesia tetap langsung muncul tanpa error.

---

## Cara Menjalankan

### Linux

```bash
# Instalasi awal (sekali saja)
./install.sh

# Menjalankan aplikasi
./manage.sh start     # Berjalan di background (buka http://127.0.0.1:8767)
./manage.sh status    # Cek status server
./manage.sh stop      # Matikan server
```

*(Atau jalankan langsung di foreground dengan `./run.sh`)*

### Windows (Portable)

1. Unduh dan ekstrak `tatap-windows-x64-portable.zip`.
2. Klik ganda **`Tatap.exe`** (memerlukan Microsoft Edge WebView2 — bawaan Windows 10/11).
3. Backend dan aplikasi akan berjalan otomatis dalam jendela native.

---

## Disclaimer & Lisensi

- **Sumber Konten**: Tatap melakukan agregasi dari situs pihak ketiga publik (`hianime.at`, embed stream, dan AniList). Tatap tidak menyimpan atau meng-host file video apa pun.
- **Penggunaan Pribadi**: Dibuat untuk konsumsi pribadi dan edukasi di komputer lokal (`127.0.0.1`).
- **Lisensi**: GPL-3.0.
