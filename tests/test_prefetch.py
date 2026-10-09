"""Unit test untuk subtitle prefetch & dedup in-flight."""
import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import main  # noqa: E402


@pytest.mark.asyncio
async def test_sub_prefetch_inflight_dedup(monkeypatch):
    """Pastikan _prewarm_sub_translation mendaftarkan job ke _SUB_INFLIGHT,
    dan panggilan simultan kedua me-reuse future yang sama tanpa duplikasi call."""
    calls = []

    async def fake_translate_job(url, referer, src, lang, key_llm, key_mt, fetcher):
        calls.append(url)
        await asyncio.sleep(0.05)
        return "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHalo dunia", {"level": "tier1"}

    async def fake_get_cache(key, ttl=None):
        return None

    monkeypatch.setattr(main, "_translate_sub_job", fake_translate_job)
    monkeypatch.setattr(main, "get_subtitle_cache", fake_get_cache)
    monkeypatch.setattr(main, "_llm_enabled", lambda: asyncio.sleep(0, result=True))

    test_url = "https://example.com/subs/en.vtt"

    # Jalankan prewarm
    await main._prewarm_sub_translation(test_url, "", "en", "id")
    assert len(main._SUB_INFLIGHT) == 1

    # Panggilan kedua saat job masih in-flight
    await main._prewarm_sub_translation(test_url, "", "en", "id")
    assert len(main._SUB_INFLIGHT) == 1
    assert len(calls) == 1  # Hanya 1 job dibuat

    # Tunggu job selesai
    await asyncio.gather(*list(main._SUB_INFLIGHT.values()))
    assert len(main._SUB_INFLIGHT) == 0
    assert len(calls) == 1
