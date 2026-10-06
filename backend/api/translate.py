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
import httpx as _httpx


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


async def call_openai_translate(cues, src, tgt, apikey, model, apiurl, timeout=60.0):
    """Translate via OpenAI-compatible /chat/completions with chunked batches.
    cues: list[{start,end,text}]. Returns translated cues (text replaced, timing preserved)."""
    if not cues:
        return cues
    apiurl = (apiurl or "https://api.openai.com/v1").rstrip("/")
    model = model or "openai/gpt-oss-20b"
    src_name = LANG_NAMES.get((src or "").lower(), src or "English")
    tgt_name = LANG_NAMES.get((tgt or "").lower(), tgt or "Indonesian")
    
    headers = {
        "Authorization": "Bearer " + apikey,
        "Content-Type": "application/json",
    }
    
    BATCH_SIZE = 40
    batches = [cues[i:i + BATCH_SIZE] for i in range(0, len(cues), BATCH_SIZE)]
    all_translated = []
    
    timeout_cfg = _httpx.Timeout(timeout, connect=15.0)
    async with _httpx.AsyncClient(timeout=timeout_cfg, trust_env=True) as c:
        for batch in batches:
            lines = [cue["text"].replace("\n", " ").strip() for cue in batch]
            body_text = "\n".join(lines)
            prompt = (
                f"Translate each subtitle line below from {src_name} to {tgt_name}.\n"
                f"Return exactly one translated line per input line, in the same order.\n"
                f"Output only the translations in {tgt_name}, no numbering, explanations, or commentary."
            )
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": f"You are a professional subtitle translator translating into natural, fluent {tgt_name}."},
                    {"role": "user", "content": prompt + "\n\n" + body_text},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            }
            if "groq.com" in apiurl:
                payload["reasoning_format"] = "hidden"
            
            translated = []
            for attempt in range(2):
                try:
                    r = await c.post(apiurl + "/chat/completions", json=payload, headers=headers)
                    if r.status_code == 400 and "reasoning_format" in payload:
                        payload.pop("reasoning_format", None)
                        r = await c.post(apiurl + "/chat/completions", json=payload, headers=headers)
                    r.raise_for_status()
                    d = r.json()
                    msg = (d.get("choices") or [{}])[0].get("message", {})
                    content = msg.get("content", "").strip()
                    translated = [x.strip() for x in content.split("\n") if x.strip() != ""]
                    if translated:
                        break
                except Exception:
                    translated = []
            
            # Pad / truncate to match batch cue count
            if len(translated) < len(lines):
                translated = translated + lines[len(translated):]
            elif len(translated) > len(lines):
                translated = translated[:len(lines)]
            
            all_translated.extend(translated)
    
    # Validasi: pastikan ada baris yang berhasil diterjemahkan
    changed_count = sum(1 for i, c in enumerate(cues) if i < len(all_translated) and all_translated[i] != c["text"])
    if changed_count == 0:
        raise RuntimeError("Translation returned no translated lines")
    
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