"""Subtitle translation module.

Multi-tier fallback translate subtitle cues:
  Tier 1: OpenAI-compatible API (Groq / OpenAI / OpenRouter, default: gpt-oss-20b via Groq)
  Tier 2: MyMemory REST API publik (gratis, 5000 char/day per IP, soft limit 4500)
  Tier 3: source English original (no translation)

Backend pakai layer ini dengan signature:
    translated_cues, tier = translate_cues_with_fallback(cues, src, tgt, apikey, model, apiurl)
"""
import re as _re
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
            text_lines = []
            for ln in buf:
                text_lines.append(ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            text_lines = [_re.sub(r"&lt;[^&]*?&gt;", "", x) for x in text_lines]
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


def _parse_llm_response(content: str, is_google: bool = False):
    """Robust parser untuk respons LLM berupa JSON array atau multi-line strings."""
    if not content:
        return []
    text = content.strip()
    if text.startswith("```"):
        text = _re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = _re.sub(r"\n?```$", "", text).strip()

    if is_google or text.startswith("["):
        # 1. Coba standard json.loads
        try:
            val = _json.loads(text)
            if isinstance(val, list):
                return [str(x).strip() for x in val]
        except Exception:
            pass

        # 2. Ekstrak blok JSON array [ ... ] dengan regex jika ada quote bermasalah
        m = _re.search(r"\[\s*(.*)\s*\]", text, _re.DOTALL)
        if m:
            inner = m.group(1)
            items = _re.findall(r"\"((?:[^\"\\]|\\.)*)\"", inner)
            if items:
                out = []
                for x in items:
                    try:
                        out.append(x.encode("utf-8").decode("unicode_escape").strip())
                    except Exception:
                        out.append(x.strip())
                return out

    # 3. Fallback: line-by-line parsing (OpenAI format atau numbering)
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Bersihkan leading bullet / numbering seperti "1. Halo" atau "1) Halo"
        cleaned = _re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


async def call_openai_translate(cues, src, tgt, apikey, model, apiurl, timeout=60.0):
    """Translate via OpenAI-compatible /chat/completions with chunked batches.
    cues: list[{start,end,text}]. Returns translated cues (text replaced, timing preserved)."""
    if not cues:
        return cues
    apikey = (apikey or "").strip().strip("\"'").strip()
    apiurl = (apiurl or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
    is_google = "googleapis.com" in apiurl
    is_ollama = "ollama.com" in apiurl
    # Model reasoning seperti gpt-oss di Ollama Cloud jauh lebih cepat & stabil dengan line-by-line text
    use_json_mode = is_google or (not is_ollama and ("groq.com" in apiurl or "openai.com" in apiurl))

    if is_google:
        if not model or model in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.8-flash"):
            model = "gemini-3.1-flash-lite"
        BATCH_SIZE = 200
    elif is_ollama:
        BATCH_SIZE = 25
    else:
        BATCH_SIZE = 60

    src_name = LANG_NAMES.get((src or "").lower(), src or "English")
    tgt_name = LANG_NAMES.get((tgt or "").lower(), tgt or "Indonesian")
    
    headers = {
        "Authorization": "Bearer " + apikey,
        "x-goog-api-key": apikey,
        "Content-Type": "application/json",
    }
    
    batches = [cues[i:i + BATCH_SIZE] for i in range(0, len(cues), BATCH_SIZE)]
    all_translated = []
    t_start = _time.time()
    prov_name = "Google AI Studio" if is_google else ("Ollama Cloud" if is_ollama else ("Groq" if "groq.com" in apiurl else "OpenAI-compatible"))
    log_translate(
        f"Mulai translate {len(cues)} cues ({src_name} -> {tgt_name}) | Provider: {prov_name} | Model: {model} | Batches: {len(batches)}"
    )
    
    timeout_cfg = _httpx.Timeout(timeout, connect=20.0)
    async with _httpx.AsyncClient(timeout=timeout_cfg, trust_env=True) as c:
        for idx, batch in enumerate(batches):
            t_batch = _time.time()
            if idx > 0:
                await _asyncio.sleep(0.3)  # Jeda aman per batch
            lines = [cue["text"].replace("\n", " ").strip() for cue in batch]
            
            system_prompt = (
                f"You are a professional anime fansub translator. Translate dialogue into natural, colloquial, spoken {tgt_name} (santai, luwes, tidak kaku, gunakan 'aku/kamu').\n"
                f"Rules:\n"
                f"1. Keep gamer/anime terms as is (e.g. NPC, quest, level, raid, guild, party, skill, boss, inventory).\n"
                f"2. Do not translate anime titles (e.g. 'Overgeared' must remain 'Overgeared').\n"
                f"3. Maintain original tone, emotion, and punctuation."
            )
            if is_ollama:
                system_prompt += "\nDo NOT explain or output reasoning thoughts. Output direct translations immediately, exactly one line per line."
            
            if use_json_mode:
                prompt = (
                    f"Translate the following JSON array of anime dialogue strings into natural, colloquial {tgt_name}.\n"
                    f"Return ONLY a valid JSON array of strings with the exact same length ({len(lines)} items) in the exact same order.\n"
                    f"Output raw JSON without markdown formatting or code blocks."
                )
                body_content = prompt + "\n\n" + _json.dumps(lines, ensure_ascii=False)
                calc_tokens = min(8192, max(2048, len(lines) * 45))
            else:
                body_text = "\n".join(lines)
                prompt = (
                    f"Translate each anime dialogue line below into natural, spoken {tgt_name} fansub.\n"
                    f"Return exactly one translated line per input line ({len(lines)} lines total), in the same order.\n"
                    f"Output only the translations in {tgt_name}, no numbering, explanations, or commentary."
                )
                body_content = prompt + "\n\n" + body_text
                calc_tokens = max(1024, min(4096, len(lines) * 60))

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body_content},
                ],
                "temperature": 0.2 if use_json_mode else 0.3,
                "max_tokens": calc_tokens,
            }
            if "groq.com" in apiurl and "gpt-oss" in model:
                payload["reasoning_format"] = "hidden"
            
            translated = []
            last_batch_err = None
            models_to_try = [model]
            if is_google:
                # Siapkan fallback otomatis jika model utama terkena rate limit (429)
                alt = "gemini-3.8-flash" if "flash-lite" in model else "gemini-3.1-flash-lite"
                models_to_try.append(alt)

            for cur_model in models_to_try:
                payload["model"] = cur_model
                for attempt in range(2):
                    try:
                        r = await c.post(apiurl + "/chat/completions", json=payload, headers=headers)
                        if r.status_code == 400 and "reasoning_format" in payload:
                            payload.pop("reasoning_format", None)
                            r = await c.post(apiurl + "/chat/completions", json=payload, headers=headers)
                        if r.status_code == 429:
                            last_batch_err = f"Rate limit (429): {_extract_err(r)}"
                            await _asyncio.sleep(2.0)
                            if is_google:
                                break
                            continue
                        if r.status_code >= 400:
                            msg = _extract_err(r)
                            last_batch_err = f"HTTP {r.status_code}: {msg}"
                            if r.status_code in (400, 401, 403):
                                raise RuntimeError(last_batch_err)
                            await _asyncio.sleep(1.0)
                            continue
                        
                        r.raise_for_status()
                        d = r.json()
                        msg = (d.get("choices") or [{}])[0].get("message", {})
                        content = msg.get("content", "").strip()
                        translated = _parse_llm_response(content, is_google=use_json_mode)
                        
                        if translated:
                            break
                        else:
                            last_batch_err = "Respon model kosong atau tidak menghasilkan translasi"
                    except RuntimeError:
                        raise
                    except Exception as ex:
                        last_batch_err = str(ex)
                        translated = []

                if translated:
                    break

            if not translated and last_batch_err:
                log_translate(f"Batch {idx+1}/{len(batches)} GAGAL: {last_batch_err}")
                raise RuntimeError(last_batch_err)
            
            dur_batch = _time.time() - t_batch
            log_translate(f"Batch {idx+1}/{len(batches)} selesai ({len(translated)} cues) dalam {dur_batch:.2f}s via {payload.get('model', model)}")
            
            # Pad / truncate to match batch cue count
            if len(translated) < len(lines):
                translated = translated + lines[len(translated):]
            elif len(translated) > len(lines):
                translated = translated[:len(lines)]
            
            all_translated.extend(translated)
    
    # Validasi: pastikan ada baris yang berhasil diterjemahkan
    changed_count = sum(1 for i, c in enumerate(cues) if i < len(all_translated) and all_translated[i] != c["text"])
    if changed_count == 0:
        log_translate("Translasi gagal: tidak ada baris yang berubah.")
        raise RuntimeError("Translation returned no translated lines")
    
    total_dur = _time.time() - t_start
    log_translate(f"Translasi AI sukses {len(cues)} cues dalam {total_dur:.2f}s ({changed_count} baris diterjemahkan)")
    
    out = []
    for i, c in enumerate(cues):
        tr_text = all_translated[i] if i < len(all_translated) else c["text"]
        out.append({"start": c["start"], "end": c["end"], "text": tr_text})
    return out


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
    log_translate(f"Mulai translate Tier 1 (Google GTX HTML-Preserved): {len(cues)} cues | {len(batches)} batches")
    
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
    log_translate(f"Sukses translate Tier 1 (Google GTX HTML): {len(cues)} cues dalam {dur:.2f}s")
    out = []
    for i, c in enumerate(cues):
        tr_text = all_translated[i] if i < len(all_translated) else c["text"]
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
            out.append({"start": cue["start"], "end": cue["end"], "text": tr})
    return out


def estimate_chars(cues):
    """Total chars for quota accounting."""
    return sum(len(c.get("text", "")) for c in (cues or []))