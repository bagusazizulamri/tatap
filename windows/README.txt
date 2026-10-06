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

SUBTITLE INDONESIA (AI TRANSLATE):
- Subtitle Indonesia tersedia via translate AI otomatis dari track English.
- Aktifkan toggle 🌐 ID di player foot bar (sebelah tombol ukuran S/M/L).
- Pilih "Indonesian (AI)" di dropdown subtitle → backend translate otomatis.
- API key gratis diperlukan untuk terjemahan berkualitas tinggi:
  - Daftar gratis di console.groq.com (Groq) atau platform.openai.com.
  - Di terminal Tatap (ketik judul), masukkan: :apikey gsk_... (Groq) atau :apikey sk-... (OpenAI).
  - Apikey otomatis terdeteksi: Groq → apiurl & model otomatis, OpenAI → auto-set juga.
  - Lihat status: :apikey | Hapus: :apikey clear | Ganti model: :model llama-3.3-70b-versatile
  - Fallback gratis: MyMemory (5000 char/hari per IP) jika belum set API key.
