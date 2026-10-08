# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, berjalan 100% di komputermu sendiri.

---

## Fitur Utama

- **Katalog & Streaming Cepat**: Pencarian judul, riwayat tontonan, rekomendasi seasonal, dan pemutaran episode multi-server.
- **Player Fleksibel**: Rasio 16:9, ambient glow, mode CRT/layar tabung, selector resolusi, dan kontrol keyboard lengkap.
- **Auto-Translate Subtitle Indonesia (AI Fansub)**: Menerjemahkan subtitle English ke Bahasa Indonesia dengan nada percakapan fansub adaptif sesuai adegan dan genre (sekolah, misteri, mecha, olahraga, pertarungan, kuliner), bebas dari idiom kaku mesin.
- **100% Penyimpanan Lokal**: Riwayat, bookmark, dan pengaturan tersimpan di SQLite lokal (`anime.db`).
- **Pilihan Player**: Web player HTML5 bawaan atau pemutar eksternal MPV.
- **Portabel & Multi-Platform**: Tersedia executable portabel untuk Windows (WebView2) dan Linux AppImage mandiri.

---

## Petunjuk Subtitle AI (BYOK)

Tatap menggunakan konsep **BYOK (Bring Your Own Key)** agar kamu bisa menikmati terjemahan AI berkualitas fansub secara fleksibel dan gratis.

### Perintah Pemasangan Cepat di Terminal Tatap:

Ketik salah satu perintah berikut langsung di kotak pencarian / terminal Tatap:

| Perintah | Provider | Model Utama |
| :--- | :--- | :--- |
| `:ollama <api_key>` | [Ollama Cloud](https://ollama.com) | `gpt-oss:20b` *(cadangan otomatis: `gpt-oss:120b`)* |
| `:groq <api_key>` | [Groq](https://groq.com) | `llama-3.3-70b-versatile` |
| `:gemini <api_key>` | [Google AI Studio](https://aistudio.google.com) | `gemini-3.1-flash-lite` |
| `:openai <api_key>` | [OpenAI](https://platform.openai.com) | `gpt-4o-mini` |

### Perintah Bantuan:
- Cek status konfigurasi: `:apikey`
- Hapus API key: `:apikey clear`
- Ganti model manual: `:model <nama_model>`

> [!TIP]
> **Tanpa API Key?** Jika belum memasukkan API key, Tatap otomatis memakai fallback **Google GTX (Zero-Key)** sehingga subtitle Indonesia tetap langsung muncul tanpa konfigurasi awal.

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

---

## Disclaimer & Lisensi

- **Sumber Konten**: Tatap melakukan agregasi dari situs pihak ketiga publik (`hianime.at`, embed stream, dan AniList). Tatap tidak menyimpan atau meng-host file video apa pun.
- **Penggunaan Pribadi**: Dibuat untuk konsumsi pribadi dan edukasi di komputer lokal (`127.0.0.1`).
- **Lisensi**: GPL-3.0.
