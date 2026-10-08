"""Subtitle translation module.

Multi-tier fallback translate subtitle cues (orkestrasi di main._translate_with_fallback):
  Tier 1: AI Fansub LLM (OpenAI-compatible: Ollama Cloud free / Gemini / Groq / OpenRouter /
          Ollama lokal). Format ber-ID `N|teks`, batch paralel, rotasi model saat limit,
          baris yang gagal diisi Google GTX (hybrid) — tidak lagi all-or-nothing.
  Tier 2: Google GTX Web RPC (zero-key, terjemahan literal/kaku)
  Tier 3: MyMemory REST API publik (gratis, 5000 char/day per IP, soft limit 4500)
  Tier 4: source English original (no translation)

Signature utama:
    translated_cues, stats = await call_openai_translate(cues, src, tgt, apikey, model, apiurl)
"""
import re as _re
import html as _html
import json as _json
import time as _time
import asyncio as _asyncio
import collections as _collections
import datetime as _dt
import httpx as _httpx

TRANSLATE_LOGS = _collections.deque(maxlen=100)


def log_translate(msg: str):
    """Catat pesan log translasi ke ring-buffer in-memory dan stdout (flush)."""
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}"
    TRANSLATE_LOGS.append(entry)
    print(f"[TRANSLATE] {entry}", flush=True)


def get_translate_logs():
    """Ambil list log translasi terbaru."""
    return list(TRANSLATE_LOGS)



def parse_vtt(text):
    """Parse WEBVTT text ke list[{start:float, end:float, text:str}].
    Port dari app.js parseVtt() — keep logic consistent."""
    out = []
    lines = (text or "").replace("\r\n", "\n").split("\n")
    i = 0
    if lines and lines[0].startswith("WEBVTT"):
        i = 1
    start = -1.0
    end = -1.0
    buf = []
    flush = None

    def _flush():
        nonlocal start, end, buf, out
        if start >= 0 and end > start and buf:
            # Plain text: buang tag VTT/HTML (<i>, <c.x>, <00:01.000>) lalu decode entity.
            # Escaping HTML dilakukan frontend (parseVtt) saat render, bukan di sini.
            text_lines = [_html.unescape(_re.sub(r"<[^>]*>", "", ln)).strip() for ln in buf]
            text_lines = [x for x in text_lines if x]
            if text_lines:
                out.append({"start": start, "end": end, "text": "\n".join(text_lines)})
        start = -1.0
        end = -1.0
        buf = []

    flush = _flush
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            _flush()
            i += 1
            continue
        if "-->" in ln:
            _flush()
            p = ln.split("-->")
            start = _vtt_ts(p[0].strip())
            end = _vtt_ts((p[1] or "").strip().split(" ")[0])
            i += 1
            continue
        if _re.match(r"^(NOTE|STYLE|REGION)", ln):
            i += 1
            continue
        if start >= 0:
            buf.append(ln)
        i += 1
    _flush()
    return out


def _vtt_ts(s):
    """Parse VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) to seconds."""
    m = _re.match(r"^(?:(\d+):)?([0-5]?\d):([0-5]\d)(?:[.,](\d{1,3}))?$", (s or "").strip())
    if not m:
        return -1.0
    ms = int((m.group(4) + "000")[:3]) if m.group(4) else 0
    return (int(m.group(1)) * 3600 if m.group(1) else 0) + int(m.group(2)) * 60 + int(m.group(3)) + ms / 1000.0


def build_vtt(cues):
    """Reconstruct WEBVTT text dari cues."""
    out = ["WEBVTT", ""]
    for c in cues:
        s = c["start"]
        e = c["end"]
        out.append(f"{_fmt_ts(s)} --> {_fmt_ts(e)}")
        out.append(c["text"])
        out.append("")
    return "\n".join(out)


def _fmt_ts(seconds):
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


LANG_NAMES = {
    "en": "English",
    "id": "Indonesian",
    "ja": "Japanese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "ru": "Russian",
    "th": "Thai",
    "vi": "Vietnamese",
    "tr": "Turkish",
    "hi": "Hindi",
}


def _extract_err(resp):
    """Ekstrak pesan error dari response HTTP OpenAI/Gemini/Groq."""
    raw_msg = ""
    try:
        j = resp.json()
        if isinstance(j, list) and len(j) > 0:
            j = j[0]
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                raw_msg = err.get("message") or err.get("code") or str(err)
            elif err:
                raw_msg = str(err)
            elif "message" in j:
                raw_msg = str(j["message"])
    except Exception:
        pass
    if not raw_msg:
        txt = (resp.text or "").strip()
        raw_msg = txt[:120] if txt else f"HTTP {resp.status_code}"

    # Deteksi pesan error spesifik Google AI Studio key
    low = raw_msg.lower()
    if "api key not valid" in low or "pass a valid api key" in low or "api_key_invalid" in low or "invalid auth key" in low:
        return "API Key Google tidak valid. Dapatkan kunci terbaru (awalan AQ...) di aistudio.google.com"
    return raw_msg


# ---------------------------------------------------------------------------
# Tier 1: AI Fansub (LLM, OpenAI-compatible)
# ---------------------------------------------------------------------------

# Model Ollama Cloud yang masuk Free plan (khusus gpt-oss)
OLLAMA_FREE_MODELS = ["gpt-oss:20b", "gpt-oss:120b"]

# Normalisasi penamaan model lama ke gpt-oss:20b
_LEGACY_MODEL_UPGRADE = {
    "ollama": {
        "gemma4:31b": "gpt-oss:20b",
        "gemma3:12b": "gpt-oss:20b",
        "gemma4": "gpt-oss:20b",
        "gpt-oss:20b-cloud": "gpt-oss:20b",
        "gpt-oss-20b": "gpt-oss:20b",
    },
}

_DEFAULT_MODEL = {
    "ollama": "gpt-oss:20b",
    "ollama_local": "gpt-oss:20b",
    "google": "gemini-3.1-flash-lite",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "google/gemini-2.0-flash-exp:free",
    "openai": "gpt-4o-mini",
    "custom": "gpt-4o-mini",
}

# batch = jumlah cue per request, conc = request paralel.
_PROVIDER_CFG = {
    "google": {"batch": 80, "conc": 2},
    "ollama": {"batch": 30, "conc": 3},
    "ollama_local": {"batch": 20, "conc": 1},
    "groq": {"batch": 40, "conc": 2},
    "openrouter": {"batch": 40, "conc": 2},
    "openai": {"batch": 60, "conc": 3},
    "custom": {"batch": 40, "conc": 2},
}

_PROVIDER_LABEL = {
    "google": "Google AI Studio", "ollama": "Ollama Cloud", "ollama_local": "Ollama Lokal",
    "groq": "Groq", "openrouter": "OpenRouter", "openai": "OpenAI", "custom": "OpenAI-compatible",
}


def is_local_llm(apiurl: str) -> bool:
    """True kalau endpoint LLM berjalan di mesin lokal (tidak butuh API key)."""
    u = (apiurl or "").lower()
    return any(h in u for h in ("://localhost", "://127.0.0.1", "://0.0.0.0", "://[::1]"))


def detect_provider(apiurl: str) -> str:
    u = (apiurl or "").lower()
    if "googleapis.com" in u:
        return "google"
    if "ollama.com" in u:
        return "ollama"
    if is_local_llm(u):
        return "ollama_local"
    if "groq.com" in u:
        return "groq"
    if "openrouter.ai" in u:
        return "openrouter"
    if "openai.com" in u:
        return "openai"
    return "custom"


def _model_chain(prov: str, model: str):
    """Urutan model yang dicoba; model berikutnya dipakai saat limit/402/404."""
    chain = [model]
    if prov == "ollama":
        chain += OLLAMA_FREE_MODELS
    elif prov == "google":
        chain.append("gemini-3.8-flash" if "flash-lite" in model else "gemini-3.1-flash-lite")
    elif prov == "groq":
        chain.append("llama-3.3-70b-versatile")
    seen, out = set(), []
    for m in chain:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


_FANSUB_PROMPT_ID = """Kamu adalah penerjemah fansub anime Indonesia berpengalaman. Terjemahkan subtitle {src} menjadi bahasa Indonesia yang luwes, enak dibaca, dan adaptif mengikuti situasi adegan (scene) — BUKAN bahasa kaku ala mesin penerjemah.

Aturan Nada Bahasa Sesuai Konteks Adegan:
1. Adegan Formal / Berwibawa / Kerajaan / Militer:
   - Situasi: Audiensi raja/bangsawan/tetua, ksatria melapor ke komandan, pidato resmi, pelayan/maid melayani tuannya, adegan ritual.
   - Kata ganti: "Saya/Anda", "Tuan/Nona", "Paduka/Yang Mulia", "Hamba", "Pangeran/Tuan Putri".
   - Nada bicara: Baku, sopan, berwibawa, dan elegan ("tidak", "sudah", "hanya", "mohon", "baiklah").
   - DILARANG menyisipkan partikel gaul santai ("nggak", "kok", "sih", "deh", "dong") ke dalam dialog formal ini.

2. Adegan Santai / Sehari-hari / Komedi / Sekolah:
   - Situasi: Percakapan teman sebaya, keluarga, interaksi di kedai, komedi/romansa.
   - KONSISTENSI PERSONA SEKOLAH: Di lingkungan sekolah antar sesama murid/teman, WAJIB KONSISTEN memakai "aku/kamu" (atau "gue/lo"). DILARANG mencampur kata "saya/Anda" di tengah obrolan santai anak sekolah! (Contoh SALAH: "dia di kelas saya" -> BENAR: "dia di kelasku").
   - Nada bicara: Bahasa lisan santai fansub ("nggak", "udah", "aja", "banget", "kok", "sih", "deh", "kan", "nih", "lho", "gimana", "kenapa", "kayak", "emang", "beneran", "dengerin", "liat").
   - Panggilan pihak ketiga: "cowok itu", "cewek itu", "dia" (JANGAN gunakan "lelaki itu", "wanita itu", "gadis tersebut").

3. Adegan Kasar / Preman / Musuh:
   - Situasi: Karakter berandalan/kasar, musuh meremehkan lawan, umpatan pertarungan.
   - Kata ganti: "gue/lo", dengan umpatan wajar ("brengsek", "sialan", "kurang ajar").

Kosakata Game, Isekai & Job System:
- Terjemahkan istilah game & isekai secara wajar dan alami (bisa memakai padanan umum Indonesia yang lazim di fansub):
  * "Quest / Mission" -> "Misi" (atau "quest")
  * "Party" -> "Kelompok" / "Tim" (atau "party")
  * "Skill" -> "Keahlian" / "Jurus" / "Kemampuan" / "Skill"
  * "Magic" -> "Sihir"
  * "Item" -> "Barang" / "Item"
  * "Dungeon" -> "Dungeon" / "Labirin" (JANGAN gunakan istilah kaku "penjara bawah tanah")
  * "Monster" -> "Monster"
  * "Level up" -> "Naik level"
  * "Inventory" -> "Penyimpanan" / "Inventori"
  * "Boss" -> "Bos" / "Boss"
  * "Guild" -> "Guild"
- Sistem Profesi / Job System:
  * "Job / Class" -> "Kelas" / "Profesi" / "Job" (misal: "What is your job/class?" -> "Apa kelasmu? / Apa profesimu?")
  * "Job change / Class advancement" -> "Ganti job" / "Pindah kelas" / "Naik kelas"
  * "Role" -> "Peran" (Tank, DPS, Healer, Support)
  * "Warrior / Fighter" -> "Pejuang" / "Petarung" / "Warrior"
  * "Knight / Paladin" -> "Ksatria" / "Paladin"
  * "Swordsman" -> "Pendekar Pedang" / "Ahli Pedang"
  * "Berserker" -> "Berserker"
  * "Tank / Guardian" -> "Tank" / "Pelindung"
  * "Archer / Hunter" -> "Pemanah" / "Pemburu"
  * "Ranger" -> "Ranger" / "Pengembara"
  * "Thief / Rogue" -> "Pencuri" / "Rogue"
  * "Assassin" -> "Pembunuh bayaran" / "Assassin"
  * "Mage / Wizard" -> "Penyihir" / "Mage"
  * "Necromancer" -> "Necromancer" / "Pembangkit mayat"
  * "Sage" -> "Sage" / "Orang Bijak"
  * "Healer / Priest / Cleric" -> "Penyembuh" / "Pendeta" / "Cleric" / "Healer"
  * "Saint / Saintess" -> "Orang Suci" / "Santa"
  * "Tamer / Beast Tamer" -> "Penjinak" / "Penjinak Monster"
  * "Summoner" -> "Pemanggil" / "Summoner"
  * "Blacksmith" -> "Pandai Besi"
  * "Alchemist" -> "Alkemis"
  * "Hero" -> "Pahlawan"
  * "Demon Lord" -> "Raja Iblis"
  * "Novice" -> "Pemula" / "Novice"

Kosakata Mecha & Pertempuran Robot / Taktis Militer (Mecha & Tactical Sci-Fi):
- "All units, sortie! / Sortie immediately!" -> "Semua unit, segera meluncur / berangkat bertempur / bersiap berangkat!" (JANGAN: "segera keluar").
- "Target locked on / lock-on" -> "Target terkunci!"
- "Take evasive action!" -> "Lakukan manuver menghindar! / Menghindar!" (JANGAN: "Ambil tindakan menghindar").
- "Direct hit / took a direct hit" -> "Kena telak! / Terkena tembakan langsung!" (JANGAN: "Pukulan langsung").
- "Emergency ejection system / eject!" -> "Sistem ejeksi darurat / lontarkan diri!" (JANGAN: "Sistem peluncuran darurat").
- "Energy filler / energy pack" -> "Energy filler / paket energi / cadangan energi" (JANGAN: "Penampung energi").
- "Fire at will!" -> "Bebas tembak! / Tembak sesuka hati!" (JANGAN: "Tembak sesuai keinginan").
- "All hail [Empire/Britannia]!" -> "Hidup [Britannia]! / Jayalah [Britannia]!" (JANGAN: "Semua bersorak").
- "Checkmate" -> "Skakmat" (JANGAN biarkan "Checkmate" jika teks dialog fansub).
- "Caught in the crossfire" -> "Terjebak dalam baku tembak / terkena baku tembak" (JANGAN: "Tertangkap dalam tembakan silang").
- "Surrender unconditionally" -> "Menyerahlah tanpa syarat!" (JANGAN: "Tundukkan tanpa syarat").
- "In the belly of the beast" -> "Di sarang musuh / di mulut singa" (JANGAN harfiah: "Di perut binatang").
- "Dance right into my trap" -> "Masuk tepat ke dalam jebakanku / masuk ke perangkapku" (JANGAN: "Menari ke jebakan").
- "Pulling the strings / who is pulling the strings?" -> "Mengendalikan semuanya / siapa dalang di balik semua ini?" (JANGAN: "memegang tali").
- "Honorary citizen" -> "Warga kehormatan" (JANGAN: "warga harta karun").
- "Ceasefire / cease fire!" -> "Gencatan senjata! / Hentikan tembakan!"

Kosakata Supranatural & Cerita Hantu Sekolah (Supernatural / School Ghost Stories):
- "Old school building / old schoolhouse" -> "Gedung sekolah lama / gedung sekolah tua"
- "Ghost journal / spiritual diary" -> "Buku harian hantu / jurnal hantu / buku catatan hantu" (JANGAN: "Buku spiritual").
- "Put [evil spirits / ghosts] to sleep / put to rest" -> "Menidurkan / menenangkan [roh / arwah / hantu]" (JANGAN: "Ngendang roh supaya tidur").
- "Seal [a ghost / spirit / demon]" -> "Menyegel [hantu / roh / siluman]" (JANGAN: "Tutup hantu / tutup nasib").
- "Spiritual seal / talisman" -> "Segel spiritual / jimat pengusir arwah / jimat" (JANGAN biarkan "talisman" kaku).
- "Possess / possessed" -> "Merasuki / kerasukan / merasuk ke dalam" (JANGAN: "Memikat").
- "Demon / fiend / youkai" -> "Siluman / iblis / monster / youkai" (JANGAN acak jadi "naga").
- "Camphor tree" -> "Pohon kamper / pohon kapur barus" (JANGAN: "Pohon kapur tulis").
- "Scaredy-cat" -> "Penakut / pengecut" (JANGAN: "Kucing takut").
- "Pull yourself together!" -> "Kuatkan dirimu! / Tenangkan dirimu! / Sadarlah!" (JANGAN: "Kumpulin diri!").
- "Echoing" (in empty hallway) -> "Bergema" (JANGAN: "Yang gema").

Kosakata Misteri Sekolah & Klub Sastra (School Mystery / Club Anime - e.g. Hyouka):
- "Classic Lit Club / Classic Literature Club" -> "Klub Sastra Klasik" (JANGAN biarkan "Classic Lit").
- "Pay my respects" (kunjungan ke klub/salam kenal) -> "Memberi salam / menyapa" (JANGAN diartikan "ngelamun").
- "Energy conservation / energy-conserving / energy saver" -> "Hemat energi / menghemat energi"
- "Energy-consuming" -> "Boros energi / menghabiskan banyak energi" (JANGAN tertukar jadi "hemat energi").
- "I'm curious! / I am curious" -> "Aku penasaran! / Aku penasaran sekali!"
- "A database cannot draw conclusions" -> "Database tidak bisa menarik kesimpulan"
- "Peeping Tom" -> "Tukang intip / pengintip"
- "After-school rendezvous" -> "Pertemuan sepulang sekolah / kencan sepulang sekolah"
- Karakter perempuan anggun/sopan (seperti Chitanda): Wajib bertutur kata sopan ("aku/kamu", santun), JANGAN gunakan "gue/lo".

Kosakata Anime Olahraga (Sports Anime):
- "Match" -> "Pertandingan" (JANGAN biarkan "match" jika mengacu ke permainan).
- "View" -> "Pemandangan" (JANGAN biarkan "view").
- "Looms in front of me" -> "Menjulang di depanku" (JANGAN: "Ngeliat di depan aku").
- "Coach" -> "Pelatih" (JANGAN biarkan "coach").
- "Off course" (in ball set/pass) -> "Melenceng / meleset" (JANGAN: "Off course").
- "Blow past [blockers]" -> "Menembus / menerobos [pemblokir]" (JANGAN: "Ngelupas blok").
- Istilah teknis voli/olahraga (Toss, Spike, Serve, Libero, Setter, Block, Match point, Time out) boleh tetap digunakan sesuai tradisi fansub olahraga.

Dilarang Terjemahkan Idiom Secara Harfiah (Gunakan Padanan Fansub Alami):
- "Aiming high" -> "Incaranmu tinggi juga" / "Seleramu tinggi juga" / "Pasang target tinggi" (JANGAN: "Banjir tinggi").
- "If you ask me" -> "Kalau menurutku sih" / "Menurutku" (JANGAN: "Kalau dengerin saya").
- "Hotties / Cuties" -> "Cewek-cewek cakep / cewek-cewek manis" (JANGAN: "Koleksi hot").
- "It goes without saying" -> "Nggak usah ditanya lagi" / "Sudah jelas" (JANGAN: "Gak usah dikira").
- "High school debut" -> "Awal baru di SMA" / "Mulai masa SMA" (JANGAN: "Debut SMA saya").
- "Plug the hole / plug" -> "Menutup lubang / menyumbat" (JANGAN: "Ngeplug").
- "How dare you [do X]!" -> "Beraninya kamu [lakukan X]!" / "Kurang ajar!" (JANGAN: "Gimana sih kamu boleh [X]").
- "How dare [an amateur]..." -> "Berani-beraninya [seorang amatir]..." (JANGAN: "Gimana sih amatir bisa...").
- "Middle of nowhere" -> "Pelosok / tempat terpencil / antah-berantah" (JANGAN: "Di tengah-tengah hutan").
- "Throw a tantrum / throw tantrums" -> "Tanteum / merajuk / ngambek" (JANGAN: "Lagi marah" tanpa emosi).
- "Big baby" -> "Kayak anak kecil / cengeng banget" (JANGAN: "Anak kecil banget").
- "See? Told ya!" -> "Tuh, kan! Apa kubilang!" (JANGAN: "Lihat? Katanya!").
- "Cool your head / cool off" -> "Menenangkan pikiran / mendinginkan kepala" (JANGAN: "Dinginkan kepala di pulau").
- "Talk back to [elders]" -> "Membantah / melawan [orang tua]" (JANGAN: "Ngomong balas").
- "Secret base" -> "Markas rahasia" (JANGAN: "Basis rahasia").
- "Cicadas" -> "Tonggeret / garengpung" (JANGAN: "Katak katak").
- "Bug" (in nature context) -> "Serangga / kumbang" (JANGAN biarkan "bug" atau "kutu komputer").
- "Like hell I would! / As if!" -> "Ogah banget! / Mana sudi!" (JANGAN: "Gak bakal, bro" kaku).
- "There is no way / no way in hell" -> "Nggak mungkin banget / mana mungkin" (JANGAN: "Gak ada cara aku ngelakuin").
- "Pervert" -> "Mesum / cowok mesum / cabul" (JANGAN biarkan "pervert").
- "Defenseless" -> "Gampang tersingkap / nggak ada pertahanan" (JANGAN: "Gak aman").
- "You guys tricked me!" -> "Kalian ngerjain aku, ya?!" (JANGAN: "Kalian ngapain ngapain!").
- "The wind is troubled today..." -> "Sepertinya angin hari ini sedang resah..." (gaya puitis/dramatis).
- "Hurry, let us make haste" -> "Ayo cepat, mari bergegas" (gaya puitis komedi).
- "How suspicious is that?" / "How suspicious!" -> "Mencurigakan banget, kan?" / "Mencurigakan sekali" (JANGAN: "Berapa curiga itu").
- "How [adjective] / How [suspicious/cute/etc.]" -> "Betapa / Begitu / Banget / Sekali" (JANGAN diterjemahkan "Berapa [kata sifat]").
- "How long was I out?" / "pass out / knock out" -> "Berapa lama aku pingsan / tak sadarkan diri?" (JANGAN: "Berapa lama aku keluar").
- "Make a fortune" -> "Kaya mendadak / untung besar / dapet banyak uang" (JANGAN: "Ngasih duit jahat").
- "At this rate" -> "Kalau begini terus / kalau kayak gini terus" (JANGAN: "Dengan kecepatan kayak gini").
- "Roger that / Copy that" -> "Dimengerti / Siap / Terima" (JANGAN: "Sanggah").
- "Optical decoy" -> "Umpan optik / ilusi optik" (JANGAN: "Penipu optik").
- "Paint the coordinates" -> "Tandai / kunci koordinatnya" (JANGAN: "Cat koordinat").
- "Wipe [them] off the map" -> "Ratakan [mereka] dengan tanah / lenyapkan mereka" (JANGAN: "Hapus mereka dari peta").
- "Corporal" -> "Kopral" (JANGAN: "Korpul").
- "Sick prank" -> "Lelucon keterlaluan / lelucon menjijikkan" (JANGAN: "Lelucon aneh").
- "Childish murderer" -> "Pembunuh kekanak-kanakan" (JANGAN: "Pembunuh anak kecil").
- "The only bad guy left" -> "Satu-satunya penjahat yang tersisa" (JANGAN: "Satu-satunya jahat").
- "I will see you executed" -> "Aku akan memastikanmu dieksekusi" (JANGAN: "Aku akan melihatmu dieksekusi").
- "Righteous people" -> "Orang-orang saleh / orang-orang jujur" (JANGAN: "Orang-orang yang benar").
- "Heart failure / heart attack" -> "Serangan jantung" (JANGAN: "Gagal jantung" jika konteks death note serangan mendadak).
- "In a pool of blood" -> "Bersimbah darah / tergenang darah" (JANGAN: "Di kolam darah").
- "Blow my cover" -> "Membongkar penyamaranku / membocorkan identitasku" (JANGAN: "Bocor rahasia aku").
- "In broad daylight" -> "Di siang bolong / terang-terangan" (JANGAN: "Di siang hari" kaku).
- "Stabbed to death" -> "Ditusuk sampai mati / ditikam hingga tewas" (JANGAN: "Disayat sampai mati").
- "Caught onto our trail" -> "Menemukan jejak kita / mengendus jejak kita" (JANGAN: "Menangkap jejak kita").
- "Jellyfied / gelatinous" -> "Berubah jadi agar-agar / jadi jeli" (JANGAN: "Jellyguy").
- "Have you lost your mind?" -> "Kamu sudah gila? / Kamu kehilangan akal sehat?" (JANGAN: "Kamu kehilangan akal" tanpa 'sehat').
- "Pale as a ghost" -> "Pucat pasi / pucat bagai mayat" (JANGAN: "Pucat kayak hantu").
- "Morgue" -> "Kamar jenazah / kamar mayat" (JANGAN biarkan "morgue").
- "My poor [someone] / other half" -> "[Seseorang]ku yang malang / belahan jiwaku yang malang" (JANGAN: "yang miskin").
- "Hate being questioned" -> "Benci ditanya-tanya / tidak suka diinterogasi" (JANGAN: "Susah dipengetan").
- "Don't say that out loud" -> "Jangan katakan itu keras-keras / jangan bicara sembarangan" (JANGAN: "Jangan bilang di luar").
- "Second basement level / B2" -> "Lantai bawah tanah kedua / lantai B2" (JANGAN: "Lantai bawah dua").
- "Ghosting someone / act like someone doesn't exist" -> "Mengabaikan / menganggapnya tak kasat mata" (JANGAN biarkan "ghosting").
- "On a royal tear / on a tear / on a rampage" -> "Mengamuk hebat / bikin onar tak terkendali" (JANGAN: "Kemarahan kerajaan").
- "Harm [someone] / do harm" -> "Melukai / menyakiti [seseorang]" (JANGAN: "Ngelakuin luka").
- "Eliminate [an opponent in battle]" -> "Menghabisi / melenyapkan" (JANGAN: "Menghapus Anda").
- "Profane [God]" -> "Menodai / menistakan" (JANGAN: "Memfitnah Tuhan").
- "Brother" (in anime sibling context) -> "Kakak / Kak / Abang" (JANGAN: "Bro").
- "Face aside / [X] aside" -> "Terlepas dari wajahnya / kesampingkan soal wajahnya" (JANGAN: "Tinggalkan wajah").
- "Sustain heavy damage / heavy casualties" -> "Mengalami kerugian/kerusakan besar" (JANGAN: "Menanggung kerusakan").
- "Solo player" -> "Pemain solo" (JANGAN: "Saya sendiri").
- "Pry into" -> "Mencari tahu / ikut campur urusan" (JANGAN: "Nanya ke").
- "Clowning around / acting stupid" -> "Bercanda / main-main / konyol" (JANGAN gunakan kata terlalu kasar/aneh seperti "ngegoblok").
- "Butt heads" -> "Berselisih / bentrok / bersitegang" (JANGAN: "Bertembung kepala").
- "Rot in hell" -> "Persetan / mampus sana / pergi ke neraka" (JANGAN: "Berputus di neraka").
- "There you go again!" -> "Mulai lagi, kan!" / "Kamu kumat lagi!" (JANGAN: "Kamu lagi!").
- "Packed you a lunch / pack a lunch" -> "Membawakanmu bekal" (JANGAN: "Bungkus makan siang").
- "Mongrel" (as anime insult) -> "Anjing kampung / hewan buduk" (JANGAN: "Anjing campuran").
- "At first sight / glance" -> "Pandangan pertama / saat pertama kali bertemu" (JANGAN: "Mata pertama").
- "Miss each other / pass by" -> "Berpapasan / saling melewatkan" (JANGAN: "Kelewatan satu sama lain").
- "I see" / "I get it" -> "Begitu rupanya" / "Ooh, begitu ya" / "Paham" (JANGAN: "Aku melihat").
- "Hold on" / "Wait" -> "Tunggu sebentar!" / "Tunggu dulu!" (JANGAN: "Bertahanlah").
- "Shut up" -> "Diem!" / "Berisik!" / "Diam!" (JANGAN: "Tutup mulutmu").
- "Are you alright?" -> "Kamu nggak apa-apa?" (JANGAN: "Apakah kamu baik-baik saja").
- "Damn it" / "Damn" -> "Sial!" / "Brengsek!" / "Cih!" (JANGAN: "Terkutuklah").
- "No way" -> "Nggak mungkin!" / "Mustahil!" (JANGAN: "Tidak ada jalan").
- "Never mind" -> "Lupakan saja" / "Bukan apa-apa" / "Nggak jadi".
- "Get lost" -> "Pergi sana!" / "Enyah!".
- "Bring it on!" -> "Sini maju kalau berani!" / "Ayo lawan!".
- "Give me a break" -> "Yang bener aja!" / "Jangan bercanda!".
- "Make a move" -> "Mendekati dia" / "Mengambil tindakan".
- "Cut it out" -> "Sudahlah!" / "Hentikan!".
- "For real?" -> "Beneran?" / "Serius?".
- "No big deal" -> "Bukan masalah besar" / "Nggak apa-apa kok".
- DILARANG MEMBIARKAN KATA SIFAT INGGRIS TANPA TERJEMAHAN:
  * "Embarrassing" -> "Memalukan" / "Bikin malu" (DILARANG: "sangat embarrassing").
  * "Gross" -> "Jijik" / "Menjijikkan".
- Pertahankan nama orang, tempat, honorifik Jepang (-san, -kun, -chan, -sama, Senpai, Sensei), gagap & interjeksi emosi ("A-Apa?!", "Tch", "Hmph").
- Pertahankan token <br> untuk ganti baris dalam 1 cue.

Format Keluaran (WAJIB):
- Satu baris per input, format persis "N|terjemahan" (N = nomor input yang sama).
- DILARANG mengulang teks bahasa Inggris asal (JANGAN: "N|Teks Inggris|Terjemahan"). Cukup "N|terjemahan".
- Jumlah & nomor baris harus sama persis dengan input. Tanpa penjelasan atau markdown.

Contoh Multi-Scene:
Input:
1|Your Majesty, the vanguard knights are ready. We shall not fail your trust.
2|Great collection of hotties, huh? Aiming high, aren't you? Nibutani, huh?
3|Pretty sweet, if you ask me. It goes without saying, it was so embarrassing!
Output:
1|Yang Mulia, pasukan ksatria garis depan telah bersiap. Kami tidak akan mengecewakan kepercayaan Anda.
2|Cewek-cewek cakepnya mantap, kan? Incaranmu tinggi juga ya? Nibutani, kan?
3|Kalau menurutku sih cakep banget. Nggak usah ditanya lagi, itu memalukan banget!"""

_FANSUB_PROMPT_GENERIC = """You are an experienced anime fansub translator. Translate {src} subtitles into natural, casual, spoken {tgt} as a popular fansub release would — not stiff, literal machine translation.
- Translate meaning and emotion, not word-for-word; keep lines short and readable.
- Keep names, honorifics (-san, -kun, -chan, Senpai, Sensei), skill names and common gamer/anime terms.
- Keep stutters, interjections and emotional punctuation (?!, ..., ~). Keep the <br> token (line break inside a cue).
Output format (MANDATORY): one line per input as "N|translation" with the same N, same count and numbering, no merging/splitting, no explanations or markdown."""


def _fansub_system_prompt(src_name: str, tgt: str, tgt_name: str) -> str:
    if (tgt or "").lower() == "id":
        return _FANSUB_PROMPT_ID.format(src=src_name)
    return _FANSUB_PROMPT_GENERIC.format(src=src_name, tgt=tgt_name)


def _prep_line(text: str) -> str:
    """Cue text -> satu baris untuk prompt (newline jadi token <br>)."""
    t = (text or "").replace("\r", "")
    t = " <br> ".join(p.strip() for p in t.split("\n") if p.strip())
    return _re.sub(r"\s+", " ", t).strip()


def _restore_line(text: str) -> str:
    """Hasil model -> cue text (token <br> jadi newline, normalisasi karakter aneh)."""
    t = (text or "").replace("\u2011", "-").replace("\u2010", "-").replace("\u00a0", " ")
    t = _re.sub(r"\s*<br\s*/?>\s*", "\n", t, flags=_re.I)
    lines = [_re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")]
    return "\n".join(x for x in lines if x)


# ---------------------------------------------------------------------------
# Post-Processing Lexicon Sanitizer (Normalisasi Diksi Fansub Indonesia)
# ---------------------------------------------------------------------------

_FORMAL_INDICATORS_RE = _re.compile(
    r"\b(paduka|yang mulia|baginda|hamba|tuan putri|pangeran|yang terhormat|jenderal|komandan|"
    r"nona besar|tuan muda|tuanku|saya mohon|letnan|kapten|mayor|kolonel|sersan|kopral|markas besar|"
    r"kekaisaran|pasukan|prajurit|panglima|inspektur)\b",
    _re.I
)

# Aturan universal: selalu dikoreksi (karena merupakan blunder/calque harfiah).
_UNIVERSAL_FANSUB_RULES = [
    (r"\bapakah kamu\b", "kamu"),
    (r"\bapakah kau\b", "kamu"),
    (r"\bapakah anda\b", "Anda"),
    (r"\bapakah dia\b", "dia"),
    (r"\bapakah mereka\b", "mereka"),
    (r"\bapakah kita\b", "kita"),
    (r"\bapakah ini\b", "ini"),
    (r"\bapakah itu\b", "itu"),
    (r"\bapakah ada\b", "ada"),
    (r"\bapakah bisa\b", "bisa"),
    (r"\bapakah benar\b", "beneran"),
    (r"\bapakah sungguh\b", "beneran"),
    (r"\bterkutuklah\b", "sial"),
    (r"\bbawalah itu\b", "sini maju"),
    (r"\bpenjara bawah tanah\b", "dungeon"),
    (r"\bserikat petualang\b", "guild petualang"),
    (r"\bbanjir tinggi\b", "incaranmu tinggi juga"),
    (r"\bsangat embarrassing\b", "memalukan banget"),
    (r"\bembarrassing\b", "memalukan"),
    (r"\bdiharamkan masuk\b", "dilarang masuk"),
    (r"\bdi mata pertama\b", "pada pandangan pertama"),
    (r"\bmata pertama\b", "pandangan pertama"),
    (r"\bngeplug\b", "menutup"),
    (r"\bngegoblok\b", "bertingkah konyol"),
    (r"\bkelewatan satu sama lain\b", "berpapasan"),
    (r"\bberapa curiga itu\b", "mencurigakan banget, kan"),
    (r"\bberapa curiganya\b", "mencurigakan"),
    (r"\bberapa curiga\b", "mencurigakan"),
    (r"\bberapa lama aku keluar\b", "berapa lama aku pingsan"),
    (r"\bduit jahat\b", "untung besar"),
    (r"\buang jahat\b", "untung besar"),
    (r"\bdengan kecepatan kayak gini\b", "kalau begini terus"),
    (r"\btinggalkan wajah\b", "terlepas dari wajah"),
    (r"\bbasis rahasia\b", "markas rahasia"),
    (r"\blihat\? katanya\b", "tuh, kan! Apa kubilang"),
    (r"\bkatanya\! kamu harus santai\b", "apa kubilang! Kamu harus santai"),
    (r"\bngomong balas\b", "membantah"),
    (r"\bbertembung kepala\b", "berselisih"),
    (r"\bbertembung\b", "bentrok"),
    (r"\bberputus di neraka\b", "mampus di neraka"),
    (r"\banjing campuran\b", "anjing buduk"),
    (r"\bkemarahan kerajaan\b", "mengamuk hebat"),
    (r"\bngelakuin luka\b", "melukai"),
    (r"\bmenghapus anda\b", "menghabisi Anda"),
    (r"\bmenghapus kamu\b", "menghabisi kamu"),
    (r"\bpenipu optik\b", "umpan optik"),
    (r"\bkorpul\b", "kopral"),
    (r"\bsanggah, ma'am\b", "siap, Ma'am"),
    (r"\bsanggah, sir\b", "siap, Sir"),
    (r"\bkalian ngapain ngapain\b", "kalian ngerjain aku ya"),
    (r"\bgak ada cara aku ngelakuin itu\b", "mana sudi aku ngelakuin itu"),
    (r"\bgak ada cara aku ngelakuin\b", "mana sudi aku ngelakuin"),
    (r"\bdasar kau pervert\b", "dasar mesum"),
    (r"\bdasar kamu pervert\b", "dasar mesum"),
    (r"\bkau pervert\b", "dasar mesum"),
    (r"\bkamu pervert\b", "dasar mesum"),
    (r"\bpervert\b", "mesum"),
    (r"\bpembunuh anak kecil\b", "pembunuh kekanak-kanakan"),
    (r"\bsatu-satunya jahat yang tersisa\b", "satu-satunya penjahat yang tersisa"),
    (r"\bsatu-satunya jahat\b", "satu-satunya penjahat"),
    (r"\bmelihatmu dieksekusi\b", "memastikanmu dieksekusi"),
    (r"\blantai bawah dua\b", "lantai bawah tanah kedua"),
    (r"\bmorgue\b", "kamar jenazah"),
    (r"\bjangan bilang itu di luar\b", "jangan katakan itu keras-keras"),
    (r"\bngelupas blok\b", "menerobos blok"),
    (r"\bngeliat di depan aku\b", "menjulang di depanku"),
    (r"\bngeliat di depanku\b", "menjulang di depanku"),
    (r"\bdi kolam darah\b", "bersimbah darah"),
    (r"\bterbaring di kolam darah\b", "terbaring bersimbah darah"),
    (r"\bdisayat sampai mati\b", "ditusuk sampai mati"),
    (r"\bmenegaskan nasib kita\b", "menentukan nasib kita"),
    (r"\bmenegaskan nasib\b", "menentukan nasib"),
    (r"\btutup nasib kita\b", "menentukan nasib kita"),
    (r"\btutup nasib\b", "menentukan nasib"),
    (r"\bmenegaskan begitu banyak hantu\b", "menyegel begitu banyak hantu"),
    (r"\bmenegaskan banyak hantu\b", "menyegel banyak hantu"),
    (r"\btutup banyak hantu\b", "menyegel banyak hantu"),
    (r"\bngendang roh jahat supaya tidur\b", "menenangkan roh jahat"),
    (r"\bngendang roh\b", "menenangkan roh"),
    (r"\bkucing takut\b", "penakut"),
    (r"\bkumpulin diri\b", "kuatkan dirimu"),
    (r"\byang gema di lorong\b", "yang bergema di lorong"),
    (r"\bsemua unit, segera keluar\b", "semua unit, segera meluncur"),
    (r"\bsegera keluar bertempur\b", "segera meluncur"),
    (r"\bambil tindakan menghindar\b", "lakukan manuver menghindar"),
    (r"\bterkena pukulan langsung\b", "terkena tembakan langsung"),
    (r"\bpukulan langsung ke\b", "tembakan telak ke"),
    (r"\bsistem peluncuran darurat\b", "sistem ejeksi darurat"),
    (r"\btembak sesuai keinginan\b", "bebas tembak"),
    (r"\bsemua bersorak britannia\b", "hidup Britannia"),
    (r"\btertangkap dalam tembakan silang\b", "terjebak dalam baku tembak"),
    (r"\btundukkan tanpa syarat\b", "menyerahlah tanpa syarat"),
    (r"\bdi perut binatang\b", "di sarang musuh"),
    (r"\bmenari langsung ke jebakan\b", "masuk langsung ke jebakan"),
    (r"\bmenari tepat ke perangkap\b", "masuk tepat ke perangkap"),
    (r"\bmenari ke perangkap\b", "masuk ke perangkap"),
    (r"\bmenari tepat ke jebakan\b", "masuk tepat ke jebakan"),
    (r"\bmenari ke jebakan\b", "masuk ke jebakan"),
    (r"\bmemegang tali\b", "mengendalikan semuanya"),
    (r"\bwarga harta karun\b", "warga kehormatan"),
    (r"\bcheckmate\b", "skakmat"),
    (r"\bCheckmate\b", "Skakmat"),
    (r"\bklub classic lit\b", "Klub Sastra Klasik"),
    (r"\bKlub Classic Lit\b", "Klub Sastra Klasik"),
    (r"\bdatang buat ngelamun\b", "datang untuk memberi salam"),
    (r"\bpeeping tom\b", "tukang intip"),
    (r"\bPeeping Tom\b", "tukang intip"),
]

# Aturan khusus adegan kasual/santai (tidak diterapkan jika konteks formal/kerajaan).
_CASUAL_FANSUB_RULES = [
    (r"\bkoleksi hotnya\b", "cewek-cewek cakepnya"),
    (r"\bkoleksi hot\b", "cewek-cewek cakep"),
    (r"\bkalau dengerin saya\b", "kalau menurutku sih"),
    (r"\bkalau dengerin aku\b", "kalau menurutku sih"),
    (r"\bgak usah dikira\b", "nggak usah ditanya lagi"),
    (r"\bbertahanlah\b", "tunggu sebentar"),
    (r"\baku melihat\b", "begitu rupanya"),
    (r"\bkulihat\b", "begitu rupanya"),
    (r"\btidak apa-apa\b", "nggak apa-apa"),
    (r"\btak apa-apa\b", "nggak apa-apa"),
    (r"\btak apa\b", "nggak apa-apa"),
    (r"\bbaik-baik saja\b", "nggak apa-apa"),
    (r"\btutup mulutmu\b", "diem"),
    (r"\btidak ada jalan\b", "nggak mungkin"),
    (r"\btidak mungkin\b", "nggak mungkin"),
    (r"\btidak bisa\b", "nggak bisa"),
    (r"\btak bisa\b", "nggak bisa"),
    (r"\btidak dapat\b", "nggak bisa"),
    (r"\btidak akan\b", "nggak bakal"),
    (r"\btak akan\b", "nggak bakal"),
    (r"\btidak tahu\b", "nggak tahu"),
    (r"\btak tahu\b", "nggak tahu"),
    (r"\btidak mau\b", "nggak mau"),
    (r"\btak mau\b", "nggak mau"),
    (r"\btidak pernah\b", "nggak pernah"),
    (r"\btak pernah\b", "nggak pernah"),
    (r"\btidak perlu\b", "nggak usah"),
    (r"\btak perlu\b", "nggak usah"),
    (r"\btidak usah\b", "nggak usah"),
    (r"\btidak boleh\b", "nggak boleh"),
    (r"\btak boleh\b", "nggak boleh"),
    (r"\btidak ada\b", "nggak ada"),
    (r"\btak ada\b", "nggak ada"),
    (r"\bsudah\b", "udah"),
    (r"\bsaja\b", "aja"),
    (r"\bhanya saja\b", "cuma"),
    (r"\bhanya\b", "cuma"),
    (r"\bmengapa kamu\b", "kenapa kamu"),
    (r"\bmengapa kau\b", "kenapa kamu"),
    (r"\bmengapa dia\b", "kenapa dia"),
    (r"\bmengapa\b", "kenapa"),
    (r"\bbagaimana kalau\b", "gimana kalau"),
    (r"\bbagaimana jika\b", "gimana kalau"),
    (r"\bbagaimana cara\b", "gimana cara"),
    (r"\bbagaimana bisa\b", "gimana bisa"),
    (r"\blelaki itu\b", "cowok itu"),
    (r"\bpria itu\b", "cowok itu"),
    (r"\bwanita itu\b", "cewek itu"),
    (r"\bgadis itu\b", "cewek itu"),
    (r"\bwanita tersebut\b", "cewek itu"),
    (r"\blelaki tersebut\b", "cowok itu"),
    (r"\btersesatlah\b", "pergi sana"),
    (r"\bjangan khawatir\b", "tenang aja"),
    (r"\btak perlu khawatir\b", "tenang aja"),
    (r"\bterima kasih banyak\b", "makasih banyak"),
    (r"\bterima kasih\b", "makasih"),
    (r"\bdengarkan aku\b", "dengerin aku"),
    (r"\bdengarkan\b", "dengerin"),
]

_COMPILED_UNIVERSAL = [(_re.compile(pat, _re.IGNORECASE), repl) for pat, repl in _UNIVERSAL_FANSUB_RULES]
_COMPILED_CASUAL = [(_re.compile(pat, _re.IGNORECASE), repl) for pat, repl in _CASUAL_FANSUB_RULES]


def _sanitize_fansub_id(text: str) -> str:
    """Normalisasi kata kaku/literal secara adaptif (menjaga adegan formal tetap sopan)."""
    if not text:
        return text

    def _replace_match(m, repl):
        orig = m.group(0)
        if orig and orig[0].isupper():
            return repl[0].upper() + repl[1:]
        return repl

    result = text
    # 1. Jalankan koreksi universal
    for rx, repl in _COMPILED_UNIVERSAL:
        result = rx.sub(lambda m, r=repl: _replace_match(m, r), result)

    # 2. Jalankan normalisasi santai jika BUKAN adegan formal/kerajaan
    is_formal = bool(_FORMAL_INDICATORS_RE.search(result))
    if not is_formal:
        for rx, repl in _COMPILED_CASUAL:
            result = rx.sub(lambda m, r=repl: _replace_match(m, r), result)

    return result


_ID_LINE_RE = _re.compile(r"^\s*(?:\*\*)?(\d{1,4})(?:\*\*)?\s*[|｜]\s?(.*)$")


def _parse_id_lines(content: str, valid_ids) -> dict:
    """Parse respons "N|teks" -> {N: teks}. Abaikan reasoning, markdown, ID di luar batch.
    Jika model mengulang teks sumber (N|source|terjemahan), ambil bagian terakhir."""
    if not content:
        return {}
    text = _re.sub(r"<think>.*?</think>", "", content, flags=_re.S | _re.I)
    text = _re.sub(r"```[a-zA-Z]*", "", text)
    out = {}
    for line in text.split("\n"):
        m = _ID_LINE_RE.match(line)
        if not m:
            continue
        i = int(m.group(1))
        t = m.group(2).strip()
        # Jika model mengulang teks input: "1|English text|Terjemahan Indonesia"
        if "|" in t or "｜" in t:
            subparts = [p.strip() for p in _re.split(r"[|｜]", t) if p.strip()]
            if len(subparts) >= 2:
                t = subparts[-1]
        if i in valid_ids and i not in out and t:
            out[i] = t
    return out


class _FatalLLMError(RuntimeError):
    """Key invalid / akses ditolak — hentikan seluruh job LLM."""


class _ModelUnavailable(RuntimeError):
    """Model tidak ada / tidak termasuk plan gratis — pindah ke model berikutnya."""


class _RateLimited(RuntimeError):
    """429 — tunggu atau pindah model."""


async def _chat_completion(client, apiurl, headers, payload) -> str:
    r = await client.post(apiurl + "/chat/completions", json=payload, headers=headers)
    if r.status_code == 400 and any(k in payload for k in ("reasoning_format", "reasoning_effort")):
        payload = {k: v for k, v in payload.items() if k not in ("reasoning_format", "reasoning_effort")}
        r = await client.post(apiurl + "/chat/completions", json=payload, headers=headers)
    if r.status_code == 429:
        raise _RateLimited(f"Rate limit (429): {_extract_err(r)}")
    if r.status_code in (401, 403):
        raise _FatalLLMError(f"HTTP {r.status_code}: {_extract_err(r)}")
    if r.status_code in (402, 404):
        raise _ModelUnavailable(f"HTTP {r.status_code}: {_extract_err(r)}")
    if r.status_code == 400:
        msg = _extract_err(r)
        if "model" in msg.lower():
            raise _ModelUnavailable(f"HTTP 400: {msg}")
        if "api key" in msg.lower() or "api_key" in msg.lower():
            raise _FatalLLMError(f"HTTP 400: {msg}")
        raise RuntimeError(f"HTTP 400: {msg}")
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {_extract_err(r)}")
    d = r.json()
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    return (msg.get("content") or "").strip()


async def call_openai_translate(cues, src, tgt, apikey, model, apiurl, timeout=120.0, fill_with_gtx=True):
    """Terjemahan gaya fansub via OpenAI-compatible /chat/completions.

    - Format ber-ID "N|teks" -> tidak ada pergeseran baris; ID yang hilang di-retry.
    - Batch paralel (per-provider), konteks 4 baris sebelumnya dikirim sebagai referensi.
    - Rotasi model saat 429/402/404 (mis. Ollama Cloud free: gpt-oss:20b -> gpt-oss:120b).
    - Cue yang tetap gagal diisi Google GTX (hybrid), bukan membuang seluruh episode.

    Return (translated_cues, stats). Raise RuntimeError kalau tidak ada satu baris pun
    yang berhasil diterjemahkan LLM.
    """
    stats = {"provider": "", "model": "", "models": {}, "llm_lines": 0, "gtx_lines": 0,
             "total": len(cues or []), "error": ""}
    if not cues:
        return cues, stats
    apikey = (apikey or "").strip().strip("\"'").strip()
    apiurl = (apiurl or "https://ollama.com/v1").strip().rstrip("/")
    prov = detect_provider(apiurl)
    model = (model or "").strip() or _DEFAULT_MODEL[prov]
    model = _LEGACY_MODEL_UPGRADE.get(prov, {}).get(model, model)
    cfg = _PROVIDER_CFG[prov]
    stats["provider"] = prov

    src_name = LANG_NAMES.get((src or "").lower(), src or "English")
    tgt_name = LANG_NAMES.get((tgt or "").lower(), tgt or "Indonesian")
    system_prompt = _fansub_system_prompt(src_name, tgt, tgt_name)

    headers = {"Content-Type": "application/json"}
    if apikey:
        headers["Authorization"] = "Bearer " + apikey
    if prov == "google":
        headers["x-goog-api-key"] = apikey
    if prov == "openrouter":
        headers["HTTP-Referer"] = "http://127.0.0.1"
        headers["X-Title"] = "Tatap"

    src_lines = [_prep_line(c["text"]) for c in cues]
    n = len(cues)
    B = cfg["batch"]
    ranges = [(lo, min(n, lo + B)) for lo in range(0, n, B)]
    state = {"models": _model_chain(prov, model), "fatal": "", "last_err": "",
             "used": _collections.Counter()}
    sem = _asyncio.Semaphore(cfg["conc"])
    t_start = _time.time()
    log_translate(
        f"Mulai AI Fansub {n} cues ({src_name} -> {tgt_name}) | Provider: {_PROVIDER_LABEL[prov]} | "
        f"Model: {' > '.join(state['models'])} | Batches: {len(ranges)} x{B} (paralel {cfg['conc']})"
    )

    def _payload(cur_model, ids, lo):
        ctx = [src_lines[j] for j in range(max(0, lo - 4), lo)]
        parts = []
        if ctx:
            parts.append("Konteks (baris sebelumnya, JANGAN diterjemahkan, hanya untuk pemahaman):\n"
                         + "\n".join("- " + x for x in ctx))
        parts.append(f"Terjemahkan {len(ids)} baris berikut:\n"
                     + "\n".join(f"{i}|{src_lines[lo + i - 1]}" for i in ids))
        reasoning = "gpt-oss" in cur_model
        p = {
            "model": cur_model,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": "\n\n".join(parts)}],
            "temperature": 0.4,
            "max_tokens": min(8192, len(ids) * 70 + 300 + (2500 if reasoning else 0)),
        }
        if reasoning:
            p["reasoning_effort"] = "low"
            if prov == "groq":
                p["reasoning_format"] = "hidden"
        return p

    async def run_batch(bidx, lo, hi, client):
        async with sem:
            got = {}
            pending = list(range(1, hi - lo + 1))
            attempts = 0
            t_b = _time.time()
            while pending and attempts < 4 and not state["fatal"] and state["models"]:
                attempts += 1
                cur_model = state["models"][0]
                try:
                    content = await _chat_completion(client, apiurl, headers, _payload(cur_model, pending, lo))
                    parsed = _parse_id_lines(content, set(pending))
                    got.update(parsed)
                    state["used"][cur_model] += len(parsed)
                    pending = [i for i in pending if i not in got]
                    if not parsed:
                        state["last_err"] = f"{cur_model}: respon kosong / format tidak sesuai"
                except _FatalLLMError as e:
                    state["fatal"] = str(e)
                    state["last_err"] = str(e)
                except (_ModelUnavailable, _RateLimited) as e:
                    state["last_err"] = f"{cur_model}: {e}"
                    only_one = len(state["models"]) == 1
                    if isinstance(e, _RateLimited) and only_one:
                        await _asyncio.sleep(2.0 * attempts + 1.0)
                        continue
                    if cur_model in state["models"] and not only_one:
                        state["models"].remove(cur_model)
                        log_translate(f"Model {cur_model} tidak tersedia/limit -> pindah ke {state['models'][0]}")
                    elif only_one:
                        state["models"].clear()
                except Exception as e:
                    state["last_err"] = f"{cur_model}: {e}"
                    await _asyncio.sleep(1.0 * attempts)
            log_translate(
                f"Batch {bidx + 1}/{len(ranges)}: {len(got)}/{hi - lo} baris AI dalam {_time.time() - t_b:.1f}s"
                + (f" (sisa {len(pending)} -> GTX)" if pending else "")
            )
            return {lo + i - 1: got[i] for i in got}

    results = {}
    timeout_cfg = _httpx.Timeout(timeout, connect=20.0)
    async with _httpx.AsyncClient(timeout=timeout_cfg, trust_env=True) as client:
        parts = await _asyncio.gather(*[run_batch(b, lo, hi, client) for b, (lo, hi) in enumerate(ranges)])
    for p in parts:
        results.update(p)

    if not results:
        err = state["fatal"] or state["last_err"] or "Model tidak menghasilkan terjemahan"
        log_translate(f"AI Fansub GAGAL total: {err}")
        raise RuntimeError(err)

    missing = [i for i in range(n) if i not in results]
    gtx_filled = {}
    if missing and fill_with_gtx:
        try:
            sub = await call_gtx_translate([cues[i] for i in missing], src, tgt)
            gtx_filled = {i: sub[k]["text"] for k, i in enumerate(missing)}
        except Exception as e:
            log_translate(f"Isi GTX untuk {len(missing)} cue gagal: {e}")

    out = []
    for i, c in enumerate(cues):
        if i in results:
            txt = _restore_line(results[i])
        else:
            txt = gtx_filled.get(i, c["text"])
        if (tgt or "").lower() == "id":
            txt = _sanitize_fansub_id(txt)
        out.append({"start": c["start"], "end": c["end"], "text": txt or c["text"]})

    used = state["used"]
    stats.update({
        "model": used.most_common(1)[0][0] if used else model,
        "models": dict(used),
        "llm_lines": len(results),
        "gtx_lines": len(gtx_filled),
        "error": state["last_err"] if missing else "",
    })
    log_translate(
        f"AI Fansub selesai {n} cues dalam {_time.time() - t_start:.1f}s | AI: {len(results)} | "
        f"GTX: {len(gtx_filled)} | model: {dict(used)}"
    )
    return out, stats


async def call_gtx_translate(cues, src="en", tgt="id", timeout=20.0):
    """Translate via Google GTX Web RPC (Unmetered, Zero-Key, Super Cepat).
    Menggunakan HTML preservation (<p id="i">...</p>) per batch (40 cues/batch).
    Google Translate menjaga 100% struktur tag HTML dan atribut id sehingga urutan dialog
    dijamin presisi dan tidak pernah bergeser atau buyar ke bahasa Inggris."""
    if not cues:
        return cues
    import urllib.request as _ur
    import urllib.parse as _up
    import re as _re
    import html as _html
    
    BATCH_SIZE = 40
    batches = [cues[i:i + BATCH_SIZE] for i in range(0, len(cues), BATCH_SIZE)]
    all_translated = []
    t_start = _time.time()
    log_translate(f"Mulai translate Google GTX (HTML-Preserved): {len(cues)} cues | {len(batches)} batches")
    
    def _fetch_batch_sync(batch_lines):
        html_chunks = []
        for i, line in enumerate(batch_lines):
            # Escape XML/HTML entities
            safe_text = _html.escape(line) if line else ""
            html_chunks.append(f'<p id="{i}">{safe_text}</p>')
        joined = "".join(html_chunks)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={tgt}&dt=t&q={_up.quote(joined)}"
        req = _ur.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "*/*"
        })
        with _ur.urlopen(req, timeout=timeout) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
            raw_out = "".join([item[0] for item in data[0] if item and item[0]])
            # Ekstrak konten per ID secara deterministik
            matches = dict(_re.findall(r'<p\s+id=[\"\']?(\d+)[\"\']?>(.*?)</p>', raw_out, _re.DOTALL))
            res = []
            for i in range(len(batch_lines)):
                if str(i) in matches:
                    unescaped = _html.unescape(matches[str(i)]).strip()
                    res.append(unescaped)
                else:
                    # Fallback ke teks awal jika ID hilang
                    res.append(batch_lines[i])
            return res

    loop = _asyncio.get_running_loop()
    for idx, batch in enumerate(batches):
        if idx > 0:
            await _asyncio.sleep(0.3)
        lines = [cue["text"].replace("\n", " ").strip() for cue in batch]
        try:
            parts = await loop.run_in_executor(None, lambda l=lines: _fetch_batch_sync(l))
            all_translated.extend(parts)
        except Exception as e:
            log_translate(f"GTX Batch {idx+1}/{len(batches)} error: {e}")
            raise e

    dur = _time.time() - t_start
    log_translate(f"Sukses translate Google GTX (HTML): {len(cues)} cues dalam {dur:.2f}s")
    out = []
    for i, c in enumerate(cues):
        tr_text = all_translated[i] if i < len(all_translated) else c["text"]
        if (tgt or "").lower() == "id":
            tr_text = _sanitize_fansub_id(tr_text)
        out.append({"start": c["start"], "end": c["end"], "text": tr_text})
    return out


async def call_mymemory_translate(cues, src, tgt, timeout=30.0):
    """Translate via MyMemory REST. Satu request per batch 1 cue.
    cues: list[{start,end,text}]. Returns translated cues."""
    if not cues:
        return cues
    out = []
    async with _httpx.AsyncClient(timeout=timeout) as c:
        for cue in cues:
            text = cue["text"]
            try:
                r = await c.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": text[:500], "langpair": f"{src}|{tgt}"},
                )
                d = r.json()
                tr = (d.get("responseData") or {}).get("translatedText", text)
                if not tr or len(tr.strip()) == 0:
                    tr = text
            except Exception:
                tr = text
            if (tgt or "").lower() == "id":
                tr = _sanitize_fansub_id(tr)
            out.append({"start": cue["start"], "end": cue["end"], "text": tr})
    return out


def estimate_chars(cues):
    """Total chars for quota accounting."""
    return sum(len(c.get("text", "")) for c in (cues or []))