"""Pre-generated speech for story mode.

Every speakable block gets one MP3, parked in Supabase Storage under a hash of
its own text, so a sentence repeated across issues — and every rerun of the same
issue — costs a HEAD rather than a synthesis. The URL rides on the block itself
(`audio` on `paragraph` and `pinyin`), which is why the client needs no hashing,
the schema needs no column, and notion_blocks_to_web stays pure.

Per block, not per card, because cards do not exist yet at this point: buildDeck
composes them at render time out of blocks that annotateBlocks has already
re-chunked and merged. The card's button plays its blocks' URLs in order.

Non-fatal by construction, like the Notion mirror — an issue with no audio is
still an issue, so callers wrap this in try/except.

Storage grows roughly 2.4 MB a day and never shrinks; the Supabase free tier is
1 GB, so pruning becomes due in about a year. To prune: list the bucket and
delete every key that appears in no row's blocks.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator

from . import http
from .furigana import is_jp_body

Block = dict[str, Any]

BUCKET = os.environ.get("TTS_BUCKET", "tts")

# Microsoft's neural voices, through the Edge browser's read-aloud service
# (the edge-tts package). Free and keyless, and for Japanese and Chinese the
# most natural of the free options. It replaced OpenAI's speech API in October
# 2026, when every request there started coming back 429 and issues went out
# silent for a week.
#
# The service is unofficial: Microsoft could close it. If it does, sentences
# simply get no clip — attach_audio is non-fatal — and the iOS app reads those
# with the phone's own voice instead.
MODEL = "edge-tts"

# (voice, rate). A native voice per language, read a touch under natural pace
# for learners. Both are part of the cache key, so changing either
# re-synthesises instead of serving the old audio.
VOICES = {
    "zh": ("zh-CN-XiaoxiaoNeural", "-10%"),
    "ja": ("ja-JP-NanamiNeural", "-10%"),
}

# A "sentence" past this is a parser bug rather than a sentence, so skip it
# instead of paying to read it aloud.
MAX_CHARS = 900

# Free, but a runaway generator hammering an unofficial service is how it gets
# closed to us. A normal issue needs 20-40.
MAX_SYNTHESES = 200

# Enough to hide the latency without looking like a flood to a free service.
WORKERS = 4

# A synthesis normally takes about a second; past this it has hung.
SYNTH_TIMEOUT = 60


def _supabase() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
    return url, key


def _cache_key(text: str, voice: str, rate: str) -> str:
    return hashlib.sha256(f"{MODEL}|{voice}|{rate}|{text}".encode()).hexdigest()[:16]


def _speakable(blocks: list[Block], lang: str) -> Iterator[tuple[Block, str]]:
    """(block, text) for everything worth reading aloud, in document order.

    zh is `pinyin` only, and that is exact rather than a heuristic:
    markers.build_blocks emits a plain paragraph in precisely two cases — a
    Korean read-through, and a line whose segmentation failed — and the
    generators already refuse to publish when failures are systemic.

    ja is `paragraph` only, gated on is_jp_body, which returns False for
    anything containing Hangul and so keeps the Korean out for free.

    `list` is excluded because notion_blocks_to_web collapses a run of bullets
    into ONE block with items[], so a single URL could not address one item.
    Toggle and callout children are excluded because in the Japanese issues the
    toggle children ARE the furigana copy — reading 漢字（かんじ） aloud would
    say every word twice.
    """
    for block in blocks:
        kind = block.get("type")
        if lang == "zh":
            if kind == "pinyin":
                text = "".join(w.get("text", "") for w in block.get("words", []))
                if text.strip():
                    yield block, text
        elif kind == "paragraph":
            text = (block.get("text") or "").strip()
            if is_jp_body(text):
                yield block, text


def _exists(public_url: str) -> bool:
    # Storage answers a missing public object with 400 rather than 404, so treat
    # anything but 200 as "synthesise". That is fail-safe: the worst case is
    # paying for one sentence twice.
    resp = http.request_with_retry("HEAD", public_url, label="Storage")
    return resp.status_code == 200


async def _speak(text: str, voice: str, rate: str) -> bytes:
    import edge_tts  # imported here so reuse-only callers need not install it

    audio = bytearray()
    stream = edge_tts.Communicate(text, voice, rate=rate).stream()
    async for chunk in stream:
        if chunk["type"] == "audio":
            audio += chunk["data"]
    if not audio:
        raise RuntimeError("edge-tts returned no audio")
    return bytes(audio)


def _synthesize(text: str, voice: str, rate: str) -> bytes:
    # Each worker thread runs its own event loop; edge-tts is async-only.
    last: Exception | None = None
    for attempt in range(3):
        try:
            return asyncio.run(asyncio.wait_for(_speak(text, voice, rate), SYNTH_TIMEOUT))
        except Exception as e:  # noqa: BLE001 — retried, then reported by the caller
            last = e
    raise RuntimeError(f"edge-tts failed after 3 attempts: {last}")


def _upload(base: str, key: str, name: str, mp3: bytes) -> None:
    resp = http.request_with_retry(
        "POST",
        f"{base}/storage/v1/object/{BUCKET}/{name}",
        label="Storage",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "audio/mpeg",
            # Content-addressed, so the object at a path never changes.
            "Cache-Control": "max-age=31536000, immutable",
            # Two generators can race between the HEAD above and this write.
            "x-upsert": "true",
        },
        data=mp3,
        timeout=60,
    )
    resp.raise_for_status()


def attach_audio(blocks: list[Block], lang: str) -> int:
    """Set `audio` on every speakable block, in place. Returns how many.

    Mutates `blocks`, which build_row_from_blocks stores by reference — so this
    still lands in the row when it runs after the row is assembled. plain_text
    is computed from text alone and is unaffected either way.
    """
    if lang not in VOICES:
        raise ValueError(f"no voice configured for {lang!r}")

    voice, rate = VOICES[lang]
    base, sb_key = _supabase()
    # A block that already has a clip keeps it: issues voiced before the move
    # to edge-tts keep their OpenAI audio when they are re-rendered.
    targets = [
        (b, t) for b, t in _speakable(blocks, lang) if len(t) <= MAX_CHARS and not b.get("audio")
    ]

    # TTS_REUSE_ONLY=1 attaches what is already in Storage and synthesises
    # nothing — for runs that should only look clips up, never make them.
    has_key = os.environ.get("TTS_REUSE_ONLY", "").strip() != "1"
    if not has_key:
        print("  ⚠ TTS_REUSE_ONLY set — reusing existing audio only.")

    # Unique texts first. A sentence repeated inside one issue is one object in
    # Storage and must be one synthesis, and deduplicating here rather than
    # inside the loop is what makes the loop safe to run concurrently.
    order: list[str] = []
    for _, text in targets:
        if text not in order:
            order.append(text)

    def url_for(text: str) -> str:
        name = f"{lang}/{_cache_key(text, voice, rate)}.mp3"
        return f"{base}/storage/v1/object/public/{BUCKET}/{name}"

    # Sequential synthesis is what timed China out: 28 sentences at roughly ten
    # seconds each ran the job past its fifteen-minute ceiling and the whole
    # issue was cancelled after the writing had already been paid for. These
    # calls are independent and almost entirely spent waiting on the network.
    done: dict[str, str] = {}
    reused = failed = missing = made = spoken_chars = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        exists = dict(zip(order, pool.map(lambda t: _exists(url_for(t)), order)))

    fresh = [t for t in order if exists[t]]
    for t in fresh:
        done[t] = url_for(t)
    reused = len(fresh)

    todo = [t for t in order if not exists[t]]
    if not has_key:
        missing = len(todo)
        todo = []
    elif len(todo) > MAX_SYNTHESES:
        print(
            f"  ⚠ audio budget ({MAX_SYNTHESES}) reached; "
            f"{len(todo) - MAX_SYNTHESES} sentence(s) stay silent."
        )
        missing = len(todo) - MAX_SYNTHESES
        todo = todo[:MAX_SYNTHESES]

    def make(text: str) -> tuple[str, str | None, str]:
        try:
            name = f"{lang}/{_cache_key(text, voice, rate)}.mp3"
            _upload(base, sb_key, name, _synthesize(text, voice, rate))
            return text, url_for(text), ""
        except Exception as e:  # noqa: BLE001 — one sentence must not stop the issue
            return text, None, str(e)

    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for text, url, err in pool.map(make, todo):
                if url:
                    done[text] = url
                    made += 1
                    spoken_chars += len(text)
                else:
                    failed += 1
                    print(f"  ⚠ audio failed for {text[:24]!r}: {err}")

    attached = 0
    for block, text in targets:
        if text in done:
            block["audio"] = done[text]
            attached += 1

    print(
        f"  audio: {attached}/{len(targets)} blocks "
        f"({made} synthesised, {reused} reused, {missing} unsynthesised, "
        f"{failed} failed) — {spoken_chars:,} chars read on {MODEL}"
    )
    return attached


def ensure_bucket() -> None:
    """Idempotent. python3 -m shared.audio --ensure-bucket"""
    base, key = _supabase()
    resp = http.request_with_retry(
        "POST",
        f"{base}/storage/v1/bucket",
        label="Storage",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "id": BUCKET,
            "name": BUCKET,
            "public": True,
            "file_size_limit": 5_242_880,
            "allowed_mime_types": ["audio/mpeg"],
        },
    )
    if resp.status_code == 409:
        print(f"bucket {BUCKET!r} already exists")
        return
    resp.raise_for_status()
    print(f"created public bucket {BUCKET!r}")


if __name__ == "__main__":
    if "--ensure-bucket" in sys.argv:
        ensure_bucket()
    else:
        print(__doc__)
