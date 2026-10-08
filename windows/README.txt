==================================================
 Tatap - Nonton Santai di Lokal (Windows Portable)
==================================================

CARA MENGGUNAKAN:
1. Cukup klik ganda "Tatap.exe".
2. Aplikasi akan langsung membuka jendela native Tatap (WebView2, bukan tab Edge).
3. Syarat: Microsoft Edge WebView2 Runtime terinstall (sudah bawaan Windows 10/11).
   Jika belum ada, Tatap menampilkan pesan berisi link unduhan resmi.
4. Tutup jendela untuk keluar; backend ikut dimatikan otomatis.
5. Untuk mematikan server secara manual kapan saja, jalankan "Stop-Tatap.bat".

DATA & LOG:
- Data riwayat tontonan dan bookmark tersimpan di "backend\anime.db".
- Log server tersimpan di "cache\server.log" (ditimpa tiap start).
- Data WebView2 tersimpan di "cache\webview2-data\".

PEMUTAR EKSTERNAL MPV (OPSIONAL):
- Secara default, video diputar langsung di dalam browser/app window.
- Jika ingin menggunakan MPV player:
  1. Unduh build MPV Windows (misal dari https://sourceforge.net/projects/mpv-player-windows/files/).
  2. Ekstrak dan taruh file "mpv.exe" ke dalam folder "bin\" di sini.
  3. Buka menu Setelan di Tatap, ubah Player menjadi "MPV".

TROUBLESHOOTING:
- Jika ingin melihat log server atau jika Tatap.exe tidak merespons, jalankan "run-console.bat".
- Seluruh aplikasi ini 100% portable: Anda dapat memindahkan folder ini ke flashdisk/drive lain tanpa perlu install ulang.

SUBTITLE INDONESIA (AI FANSUB — BYOK):
- Subtitle Indonesia tersedia via translate AI otomatis dari track English (gaya fansub santai).
- Aktifkan toggle 🌐 ID di player foot bar atau pilih "Indonesian (AI)" di dropdown subtitle.
- Pasang API key Ollama Cloud gratis milikmu:
  - Di terminal Tatap (kotak input pencarian), ketik: :ollama <api_key_kamu>
  - Tatap otomatis mengatur provider ke Ollama Cloud dan model gpt-oss:20b (cadangan: gpt-oss:120b).
- Perintah terminal:
  - Cek status: :apikey | Hapus key: :apikey clear | Ganti model: :model gpt-oss:20b
- Tanpa API Key? Google GTX (Zero-Key) otomatis aktif sebagai fallback gratis.
