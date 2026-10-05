# Tatap

> *Nonton santai di lokal* — pemutar anime berbasis web, ringan, tanpa akun, tanpa server publik. Jalan 100% di komputermu sendiri.

## Fitur

- Pencarian judul dengan saran pencarian terakhir.
- Pilih judul, lalu pilih episode dari daftar.
- Player 16:9 dengan pilihan kualitas, subtitle multi-bahasa (atau Off), dan preferensi bahasa tersimpan.
- Cahaya ambient + efek layar tabung (bisa dimatikan).
- Lanjut menonton, shortcut keyboard, riwayat lokal.
- Opsi pemutar eksternal MPV (kalau `mpv` terpasang).
- Windows: `Tatap.exe` native (WebView2), tutup jendela = backend ikut mati.

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
