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

import base64
import hashlib
import os
import sys
from typing import Any, Iterator

from . import http
from .furigana import is_jp_body

Block = dict[str, Any]

BUCKET = os.environ.get("TTS_BUCKET", "tts")
SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"

# (BCP-47 code, voice, speaking rate). The rate is part of the cache key below,
# so changing the pace re-synthesises rather than serving the old one.
#
# Slightly under natural pace on both: this doubles as listening practice. An
# unknown voice name is a 400 on EVERY call, which would silence a whole issue —
# check against list_voices() before changing either.
VOICES = {
    "zh": ("cmn-CN", "cmn-CN-Wavenet-A", 0.85),
    "ja": ("ja-JP", "ja-JP-Neural2-B", 0.95),
}

# Cloud TTS caps input at 5000 bytes. A "sentence" past this is a parser bug
# rather than a sentence, so skip it instead of failing the call.
MAX_CHARS = 900

# Every synthesis is billable, and a runaway generator is the only way this ever
# gets expensive. A normal issue needs 20-40.
MAX_SYNTHESES = 200


def _api_key() -> str:
    key = os.environ.get("GCP_TTS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GCP_TTS_API_KEY is not set")
    return key


def _supabase() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
    return url, key


def _cache_key(text: str, voice: str, rate: float) -> str:
    return hashlib.sha256(f"{voice}|{rate}|{text}".encode()).hexdigest()[:16]


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


def _synthesize(text: str, code: str, voice: str, rate: float) -> bytes:
    resp = http.request_with_retry(
        "POST",
        f"{SYNTHESIZE_URL}?key={_api_key()}",
        label="Cloud TTS",
        headers={"Content-Type": "application/json"},
        json={
            "input": {"text": text},
            "voice": {"languageCode": code, "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return base64.b64decode(resp.json()["audioContent"])


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

    code, voice, rate = VOICES[lang]
    base, sb_key = _supabase()
    targets = [(b, t) for b, t in _speakable(blocks, lang) if len(t) <= MAX_CHARS]

    # No key is reuse-only rather than nothing: whatever is already in Storage
    # still attaches. rerender.py leans on this — a keyless run that attached
    # nothing would report every row as changed and --commit would PATCH the
    # audio away.
    has_key = bool(os.environ.get("GCP_TTS_API_KEY", "").strip())
    if not has_key:
        print("  ⚠ GCP_TTS_API_KEY not set — reusing existing audio only.")

    seen: dict[str, str] = {}  # text -> url, for repeats within one issue
    attached = made = reused = missing = failed = 0

    for block, text in targets:
        try:
            url = seen.get(text)
            if url is None:
                name = f"{lang}/{_cache_key(text, voice, rate)}.mp3"
                url = f"{base}/storage/v1/object/public/{BUCKET}/{name}"
                if _exists(url):
                    reused += 1
                elif not has_key:
                    missing += 1
                    continue
                else:
                    if made >= MAX_SYNTHESES:
                        print(
                            f"  ⚠ audio budget ({MAX_SYNTHESES}) reached; "
                            "the rest of this issue stays silent."
                        )
                        break
                    _upload(base, sb_key, name, _synthesize(text, code, voice, rate))
                    made += 1
                seen[text] = url
            block["audio"] = url
            attached += 1
        except Exception as e:  # noqa: BLE001 — one sentence must not stop the issue
            failed += 1
            print(f"  ⚠ audio failed for {text[:24]!r}: {e}")

    print(
        f"  audio: {attached}/{len(targets)} blocks "
        f"({made} synthesised, {reused} reused, {missing} unsynthesised, "
        f"{failed} failed)"
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


def list_voices(code: str) -> None:
    """python3 -m shared.audio --voices cmn-CN — check a name before trusting it."""
    resp = http.request_with_retry(
        "GET", f"{VOICES_URL}?languageCode={code}&key={_api_key()}", label="Cloud TTS"
    )
    resp.raise_for_status()
    for v in resp.json().get("voices", []):
        print(f"  {v['name']:28s} {v.get('ssmlGender','?'):8s} {v.get('naturalSampleRateHertz','')}")


if __name__ == "__main__":
    if "--ensure-bucket" in sys.argv:
        ensure_bucket()
    elif "--voices" in sys.argv:
        list_voices(sys.argv[sys.argv.index("--voices") + 1])
    else:
        print(__doc__)
