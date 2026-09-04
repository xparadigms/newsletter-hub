#!/usr/bin/env python3
"""Mandarin Basics — a daily Chinese lesson, beginner to intermediate.

Not a news brief: one grammar point, new words used in real sentences, a short
dialogue and a few practice lines, at roughly HSK 2-4. Every Chinese line is
segmented into words with pinyin, and each section carries a Korean explanation.

It writes the same marker format China Daily does, so it shares
shared/markers.py and gets the pinyin rendering for free. Supabase only — no
Notion mirror, no calendar event.
"""

import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import anthropic

# The workflow runs with this project as the working directory, so the repo root
# is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio, issue as issue_row, markers, store  # noqa: E402

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
KST = timezone(timedelta(hours=9))
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))
# An extra issue for a day that already has one, requested from the site. The
# scheduled run is edition 1 and its run_key is unchanged, so nothing about the
# daily path moves.
EDITION = int(os.environ.get("EDITION", "1"))


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000

# A fixed syllabus, walked by day. A model asked for "a grammar point" with no
# memory of yesterday returns 了 and 把 over and over; indexing into a list makes
# the sequence deterministic, gives the course a shape, and means two people
# running this on the same day get the same lesson.
SYLLABUS = [
    ("是…的 강조구문", "emphasising when/where/how something happened"),
    ("동사 중첩 (看看, 试试)", "softening a verb, 'have a little look'"),
    ("把자문", "moving the object in front of the verb to say what happened to it"),
    ("비교문 比 / 没有 / 一样", "comparing two things"),
    ("정도보어 得", "saying how well an action is done"),
    ("방향보어 来 / 去", "direction of movement relative to the speaker"),
    ("가능보어 得了 / 不了", "whether an action can be completed"),
    ("결과보어 完 / 好 / 见", "the result an action reached"),
    ("이합사 (见面, 帮忙)", "verb-object words that split"),
    ("피동문 被 / 让 / 叫", "the passive"),
    ("连…也/都", "even X"),
    ("除了…以外", "besides / except"),
    ("虽然…但是 / 不但…而且", "concession and addition"),
    ("因为…所以 / 既然", "cause and consequence"),
    ("如果…就 / 要是", "conditionals"),
    ("越来越 / 越…越", "increasing degree"),
    ("快要…了 / 就要…了", "something about to happen"),
    ("一边…一边 / 一…就", "simultaneous and immediate sequence"),
    ("어기조사 吧 / 呢 / 吗 / 啊", "sentence-final particles and tone"),
    ("시량보어 (동작의 지속 시간)", "how long an action lasted"),
    ("동태조사 过", "having experienced something before"),
    ("존현문 (있다/나타나다)", "existence and appearance sentences"),
    ("반어문 不是…吗", "rhetorical questions"),
    ("离合词와 시간 표현", "time expressions with separable verbs"),
]

SETTINGS = [
    "식당", "지하철역", "회사 사무실", "카페", "병원 접수처", "은행",
    "공항 체크인", "편의점", "택시 안", "호텔 프런트", "약국", "우체국",
]


def todays_lesson() -> tuple[str, str, str]:
    """(grammar point, its one-line English gloss, dialogue setting) for today."""
    day = datetime.now(KST).timetuple().tm_yday
    grammar, gloss = SYLLABUS[day % len(SYLLABUS)]
    return grammar, gloss, SETTINGS[day % len(SETTINGS)]


SYSTEM_PROMPT = """\
You write "Mandarin Basics", a daily Chinese lesson for Heechang — a Korean \
speaker studying Mandarin. He is past the absolute basics and working towards \
intermediate: comfortable with HSK 2 vocabulary, learning HSK 3-4.

Teach in Korean, in Chinese. Every explanation is in Korean, plain and direct, \
the way a good tutor talks — no lecture, no filler. Every example is real \
Simplified Chinese someone would actually say.

Keep the Chinese at HSK 2-4. Short sentences. Common words. If a rarer word \
earns its place, it is fine, but never reach for literary or formal register \
when a everyday word does the job.
"""

LESSON_PROMPT = """\
Write today's Mandarin Basics lesson. Today is {date_line}.

Today's grammar point is: {grammar} ({gloss})
Today's dialogue setting is: {setting}

Output format — these markers and nothing else. No Markdown, no emoji, no \
bullet characters, no horizontal rules, no numbering of your own.

Line 1 must be:
SUMMARY: <one Korean sentence naming today's grammar point, at most 60 characters>

Line 2 must be:
MAIN_TITLE: <English title naming the grammar point, 8 words or fewer>

Then exactly these five sections, in this order. EVERY Chinese line is \
immediately followed by its own "> " line giving that one sentence in Korean — \
never group several translations together, and never leave a Chinese line \
without the Korean directly beneath it.

### 오늘의 문법: {grammar}
<Chinese example sentence>
> <Korean translation of that sentence, and nothing else>
<Chinese example sentence>
> <Korean translation of that sentence, and nothing else>
<Chinese example sentence>
> <Korean translation of that sentence, and nothing else>
> 설명: <Korean, two or three sentences — what the pattern does, where the \
pieces go, and one thing Korean speakers get wrong.>

### 새 단어
<Chinese sentence using new word 1>
> <Korean: 단어 — 뜻. then the sentence in Korean.>
<Chinese sentence using new word 2>
> <Korean: 단어 — 뜻. then the sentence in Korean.>
<Chinese sentence using new word 3>
> <Korean: 단어 — 뜻. then the sentence in Korean.>
<Chinese sentence using new word 4>
> <Korean: 단어 — 뜻. then the sentence in Korean.>

### 대화: {setting}
<Chinese dialogue line>
> <Korean translation of that line>
<Chinese dialogue line>
> <Korean translation of that line>
<Chinese dialogue line>
> <Korean translation of that line>
<Chinese dialogue line>
> <Korean translation of that line>
<Chinese dialogue line>
> <Korean translation of that line>
<Chinese dialogue line>
> <Korean translation of that line>

### 오늘의 표현
<Chinese sentence using a set phrase or common collocation>
> <Korean translation of that sentence>
<Chinese sentence using the same phrase in a different situation>
> <Korean translation of that sentence>
> 설명: <Korean — what the phrase means and when you would use it.>

### 연습
<Chinese practice sentence with the grammar point>
> <Korean translation of that sentence>
<Chinese practice sentence with the grammar point>
> <Korean translation of that sentence>
> 포인트: <Korean, one short line on what to notice.>

Rules that matter:

- Write ONLY Simplified Chinese in the lines under a ### heading. No \
Traditional characters, no Korean, no English in those lines.
- NEVER write pinyin or romanisation anywhere, and never put a reading in \
parentheses after a word. Readings are added afterwards by a separate tool, and \
anything you write there corrupts it.
- Each Chinese line is one sentence and at most 30 characters. These are study \
sentences; a learner should be able to hold the whole line in their head.
- A "> " line translates ONLY the single Chinese line directly above it. Do not \
write "번역:" and list several at once.
- Use today's grammar point in the 문법, 연습 and at least twice in the 대화.
- The four 새 단어 sentences must introduce four DIFFERENT new words, and each \
must be a word a learner at this level would plausibly not know yet.
"""


def generate_lesson() -> tuple[str, str, str, str]:
    """(issue_text, grammar, gloss, setting)."""
    grammar, gloss, setting = todays_lesson()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = LESSON_PROMPT.format(
        date_line=datetime.now(KST).strftime("%A, %B %d, %Y"),
        grammar=grammar,
        gloss=gloss,
        setting=setting,
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip(), grammar, gloss, setting


def _issue_title(main_title: str) -> str:
    return f"[Mandarin Basics #{ISSUE_NUMBER}] ({main_title})"


def run() -> None:
    now_kst = datetime.now(KST)
    grammar, gloss, setting = todays_lesson()
    print(f"▸ Mandarin Basics — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')}")
    print(f"  Grammar: {grammar} ({gloss})")
    print(f"  Dialogue setting: {setting}")

    print("▸ Writing the lesson via Claude...")
    issue_text, *_ = generate_lesson()

    main_title, summary = markers.parse_meta(issue_text)
    print(f"  Title: {_issue_title(main_title)}")

    print("▸ Segmenting Chinese and attaching pinyin...")
    blocks, sections, unsegmented = markers.build_blocks(issue_text)
    print(f"  {sections} sections, {len(blocks)} blocks, {unsegmented} lines unsegmented.")
    if sections < 4:
        print(f"✗ Only {sections} sections — the model ignored the lesson format.")
        sys.exit(1)
    if unsegmented > 2:
        print(f"✗ {unsegmented} lines failed segmentation — refusing to publish.")
        sys.exit(1)

    date_str = now_kst.strftime("%Y-%m-%d")
    row = issue_row.build_row_from_blocks(
        section="mandarin",
        issue_date=date_str,
        raw_title=_issue_title(main_title),
        blocks=blocks,
        source_text=issue_text,
        source_format="lesson_md",
        summary=summary,
        edition=EDITION,
    )

    if "--dry-run" in sys.argv:
        print("\n(dry run — nothing written)\n")
        print("=" * 60)
        print(issue_text)
        print("=" * 60)
        return

    print("▸ Synthesising audio...")
    try:
        audio.attach_audio(blocks, "zh")
    except Exception as e:  # noqa: BLE001 — a silent issue still publishes
        print(f"  ⚠ Audio failed (non-fatal): {e}")

    print("▸ Saving to Supabase...")
    stored = store.upsert_issue(row)
    if stored.get("slug"):
        print(f"✓ Stored: mandarin/{stored['slug']}")
        store.ping_revalidate("mandarin", stored["slug"])

    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
