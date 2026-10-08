"""Unit test engine translate subtitle (tanpa network)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from api import translate as T  # noqa: E402


def test_parse_vtt_plain_text_and_linebreak():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<i>Tom &amp; Jerry</i>\nsecond line\n"
    cues = T.parse_vtt(vtt)
    assert cues == [{"start": 1.0, "end": 2.0, "text": "Tom & Jerry\nsecond line"}]


def test_prep_restore_roundtrip():
    assert T._prep_line("Hello\nworld") == "Hello <br> world"
    assert T._restore_line("Halo <br> dunia") == "Halo\ndunia"
    assert T._restore_line("A\u2011Apa?!") == "A-Apa?!"


def test_parse_id_lines_ignores_noise_and_out_of_range():
    content = "<think>hmm</think>\n```\n1|Hello|Hei!\n**2**| Kamu ngapain?\n9|nyasar\nteks bebas\n3|\n```"
    got = T._parse_id_lines(content, {1, 2, 3})
    assert got == {1: "Hei!", 2: "Kamu ngapain?"}


def test_detect_provider():
    assert T.detect_provider("https://ollama.com/v1") == "ollama"
    assert T.detect_provider("http://localhost:11434/v1") == "ollama_local"
    assert T.detect_provider("https://generativelanguage.googleapis.com/v1beta/openai") == "google"
    assert T._model_chain("ollama", "gpt-oss:20b") == ["gpt-oss:20b", "gpt-oss:120b"]


def _cues(n):
    return [{"start": float(i), "end": i + 0.9, "text": f"line {i}"} for i in range(n)]


def test_retry_missing_ids_and_gtx_fill(monkeypatch):
    calls = []

    async def fake_chat(client, apiurl, headers, payload):
        user = payload["messages"][1]["content"]
        ids = [int(l.split("|")[0]) for l in user.split("\n") if "|" in l and l.split("|")[0].isdigit()]
        calls.append(ids)
        # Batch pertama: "lupa" id 2 (model menggabung baris); retry: kirim semua.
        if len(calls) == 1:
            return "\n".join(f"{i}|terjemahan {i}" for i in ids if i != 2)
        return "\n".join(f"{i}|terjemahan {i}" for i in ids)

    monkeypatch.setattr(T, "_chat_completion", fake_chat)
    out, stats = asyncio.run(T.call_openai_translate(_cues(3), "en", "id", "k", "gpt-oss:20b", "https://ollama.com/v1"))
    assert [c["text"] for c in out] == ["terjemahan 1", "terjemahan 2", "terjemahan 3"]
    assert calls[1] == [2]  # hanya ID yang hilang di-retry
    assert stats["llm_lines"] == 3 and stats["gtx_lines"] == 0


def test_model_rotation_and_hybrid(monkeypatch):
    async def fake_chat(client, apiurl, headers, payload):
        if payload["model"] == "gpt-oss:20b":
            raise T._RateLimited("429")
        user = payload["messages"][1]["content"]
        ids = [int(l.split("|")[0]) for l in user.split("\n") if "|" in l and l.split("|")[0].isdigit()]
        return "\n".join(f"{i}|ok {i}" for i in ids if i != 1)  # id 1 selalu hilang

    async def fake_gtx(cues, src="en", tgt="id", timeout=20.0):
        return [{**c, "text": "gtx"} for c in cues]

    monkeypatch.setattr(T, "_chat_completion", fake_chat)
    monkeypatch.setattr(T, "call_gtx_translate", fake_gtx)
    out, stats = asyncio.run(T.call_openai_translate(_cues(3), "en", "id", "k", "gpt-oss:20b", "https://ollama.com/v1"))
    assert [c["text"] for c in out] == ["gtx", "ok 2", "ok 3"]
    assert stats["model"] == "gpt-oss:120b"
    assert stats["gtx_lines"] == 1


def test_fatal_key_raises(monkeypatch):
    async def fake_chat(client, apiurl, headers, payload):
        raise T._FatalLLMError("HTTP 401: bad key")

    monkeypatch.setattr(T, "_chat_completion", fake_chat)
    try:
        asyncio.run(T.call_openai_translate(_cues(2), "en", "id", "k", "", "https://ollama.com/v1"))
        assert False, "harus raise"
    except RuntimeError as e:
        assert "401" in str(e)


def test_sanitize_fansub_id():
    # 1. Kasual / Santai
    raw1 = "Apakah kamu baik-baik saja?"
    assert T._sanitize_fansub_id(raw1) == "Kamu nggak apa-apa?"

    raw2 = "Tutup mulutmu dan dengarkan aku!"
    assert T._sanitize_fansub_id(raw2) == "Diem dan dengerin aku!"

    raw3 = "Lelaki itu sudah pergi ke serikat petualang di penjara bawah tanah."
    assert T._sanitize_fansub_id(raw3) == "Cowok itu udah pergi ke guild petualang di dungeon."

    raw4 = "Mengapa kamu tidak mau makan? Tenang saja, tidak apa-apa."
    assert T._sanitize_fansub_id(raw4) == "Kenapa kamu nggak mau makan? Tenang aja, nggak apa-apa."

    # Idiom & Diksi aneh (Chuunibyou Ep 1 calque fixes & awkward slang)
    raw5 = "Banjir tinggi, ya? Kalau dengerin saya, koleksi hotnya sangat embarrassing."
    assert T._sanitize_fansub_id(raw5) == "Incaranmu tinggi juga, ya? Kalau menurutku sih, cewek-cewek cakepnya memalukan banget."

    raw6 = "Area ini diharamkan masuk! Mereka mau ngeplug lubang itu di mata pertama."
    assert T._sanitize_fansub_id(raw6) == "Area ini dilarang masuk! Mereka mau menutup lubang itu pada pandangan pertama."

    raw7 = "Berapa curiga itu? Berapa lama aku keluar? Kamu bakal dapat duit jahat dengan kecepatan kayak gini."
    assert T._sanitize_fansub_id(raw7) == "Mencurigakan banget, kan? Berapa lama aku pingsan? Kamu bakal dapat untung besar kalau begini terus."

    raw8 = "Ini basis rahasia kita! Jangan ngomong balas ke orang tua! Lihat? Katanya!"
    assert T._sanitize_fansub_id(raw8) == "Ini markas rahasia kita! Jangan membantah ke orang tua! Tuh, kan! Apa kubilang!"

    raw9 = "Kita bertembung kepala, dasar anjing campuran! Pergi dan berputus di neraka!"
    assert T._sanitize_fansub_id(raw9) == "Kita berselisih, dasar anjing buduk! Pergi dan mampus di neraka!"

    raw10 = "Musuh sedang dalam kemarahan kerajaan. Jangan ngelakuin luka pada warga, atau aku akan menghapus kamu!"
    assert T._sanitize_fansub_id(raw10) == "Musuh sedang dalam mengamuk hebat. Jangan melukai pada warga, atau aku akan menghabisi kamu!"

    raw11 = "Korpul, aktifkan penipu optik itu! Sanggah, Ma'am!"
    assert T._sanitize_fansub_id(raw11) == "Kopral, aktifkan umpan optik itu! Siap, Ma'am!"

    raw12 = "Gak ada cara aku ngelakuin itu, dasar kau pervert! Kalian ngapain ngapain?!"
    assert T._sanitize_fansub_id(raw12) == "Mana sudi aku ngelakuin itu, dasar mesum! Kalian ngerjain aku ya?!"

    raw13 = "Kira bukan dewa, dia pembunuh anak kecil dan satu-satunya jahat yang tersisa. Aku akan melihatmu dieksekusi!"
    assert T._sanitize_fansub_id(raw13) == "Kira bukan dewa, dia pembunuh kekanak-kanakan dan satu-satunya penjahat yang tersisa. Aku akan memastikanmu dieksekusi!"

    raw14 = "Kenapa kamu ke lantai bawah dua? Morgue ada di sana, jangan bilang itu di luar!"
    assert T._sanitize_fansub_id(raw14) == "Kenapa kamu ke lantai bawah tanah kedua? Kamar jenazah ada di sana, jangan katakan itu keras-keras!"

    # 2. Formal / Kerajaan / Militer (Harus mempertahankan kata baku & sopan)
    raw_formal1 = "Yang Mulia, hamba tidak dapat menyetujui keputusan ini."
    assert T._sanitize_fansub_id(raw_formal1) == "Yang Mulia, hamba tidak dapat menyetujui keputusan ini."

    raw_formal2 = "Paduka, pasukan ksatria sudah bersiap di gerbang kota."
    assert T._sanitize_fansub_id(raw_formal2) == "Paduka, pasukan ksatria sudah bersiap di gerbang kota."

    raw_formal3 = "Letnan, kami tidak akan membiarkan musuh menembus garis pertahanan markas besar."
    assert T._sanitize_fansub_id(raw_formal3) == "Letnan, kami tidak akan membiarkan musuh menembus garis pertahanan markas besar."

