#!/usr/bin/env python3
"""Business Insight — daily business thinking from global operators, in Japanese.

Three ideas a day, each traced to a named person — a founder, an investor, an
operator — and to where they actually said it. Written in Japanese business
register with a full Korean translation under every paragraph, so it doubles as
business-Japanese practice the way Japan Daily Talk doubles as spoken practice.

Sourcing is the whole problem. "What did Bezos say today" has no feed: a
Google News query for a single name is fresh some days and empty others
(measured: Bezos 22/25 in 72h, Andreessen 2/25, Garry Tan 1/25). So the roster
is not fixed. A pool of podcasts, essays and interviews is gathered over a
seven-day window and the model picks the three best ideas from whoever actually
spoke — which is also why the lookback is a week rather than the 36 hours the
news briefs use. Podcasts publish weekly; a day-long window would come up empty.

A week-long window means yesterday's episode is still in today's pool, so the
titles of recent issues are passed in as exclusions. Without that this newsletter
would rediscover the same interview every morning, which is exactly how the
startup brief once produced four identical issues.
"""

import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import anthropic
import feedparser

# The workflow runs with this project as the working directory, so the repo root
# is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio, furigana, issue as issue_row, plaintext, store  # noqa: E402

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
KST = timezone(timedelta(hours=9))
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000

# Seven days, not 36 hours. Every source here publishes weekly at best.
LOOKBACK_DAYS = 7

_GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# Names worth a query even on a quiet week. Not a roster to be filled every day
# — the model writes about whoever actually said something worth repeating, and
# these queries only make sure the pool contains them when they did.
GOOGLE_NEWS_QUERIES = [
    '"Jeff Bezos"',
    '"Marc Andreessen"',
    '"Garry Tan"',
    '"Sam Altman"',
    '"Brian Chesky"',
    '"Satya Nadella"',
]

# Where the thinking actually lives: long-form interviews and essays, where
# someone is asked to explain how they decide things. Verified reachable and
# publishing; the per-feed try/except covers the ones that lapse.
RSS_FEEDS = {
    "a16z Podcast": "https://feeds.simplecast.com/JGE3yC0V",
    "Lenny's Newsletter": "https://lennysnewsletter.com/feed",
    "Stratechery": "https://stratechery.com/feed/",
    "SaaStr": "https://www.saastr.com/feed/",
    "All-In Podcast": "https://allinchamathjason.libsyn.com/rss",
    "Invest Like the Best": "https://feeds.megaphone.fm/investlikethebest",
    "My First Million": "https://feeds.megaphone.fm/HS2300184645",
    "TechCrunch": "https://techcrunch.com/feed/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Scrapers ────────────────────────────────────────────────────────────────
def _entries(name: str, url: str, limit: int, cutoff: datetime) -> list[dict]:
    items: list[dict] = []
    feed = feedparser.parse(url)
    for entry in feed.entries[:limit]:
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                published = datetime(*parsed[:6], tzinfo=KST)
                break
        if published and published < cutoff:
            continue
        title = getattr(entry, "title", "")
        if not title:
            continue
        # Show notes carry the substance — an episode title alone rarely says
        # what was argued, and this newsletter is about the argument.
        summary = getattr(entry, "summary", "")[:1200]
        items.append({
            "source": name,
            "text": f"{title}. {summary}" if summary else title,
            "url": getattr(entry, "link", ""),
            "date": published.isoformat() if published else "",
        })
    return items


def scrape_rss_feeds() -> list[dict]:
    cutoff = datetime.now(KST) - timedelta(days=LOOKBACK_DAYS)
    items: list[dict] = []
    for name, url in RSS_FEEDS.items():
        try:
            found = _entries(name, url, 25, cutoff)
            items.extend(found)
            if not found:
                print(f"  ⚠ {name} had nothing in the last {LOOKBACK_DAYS} days")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Failed to parse {name}: {e}")
    return items


def scrape_google_news() -> list[dict]:
    cutoff = datetime.now(KST) - timedelta(days=LOOKBACK_DAYS)
    items: list[dict] = []
    for query in GOOGLE_NEWS_QUERIES:
        try:
            items.extend(_entries(f"Google News/{query}", _GNEWS.format(q=quote(query)), 15, cutoff))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Google News {query} failed: {e}")
    return items


def dedupe(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        out.append(item)
    return out


# ── LLM ─────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are the writer of "Business Insight", a daily Japanese newsletter for a \
reader who runs a company and reads Japanese at roughly N3-N2.

Never name his company or write about his industry specifically. The insights \
are general business thinking, useful to anyone running or building something.

Each issue explains four pieces of business thinking from named global \
operators: founders, investors, VCs, executives. Jeff Bezos, Marc Andreessen, \
Garry Tan, Sam Altman, Brian Chesky, Sarah Guo — whoever actually said \
something worth repeating this week.

WHAT AN INSIGHT IS: a way of deciding, judging or building that transfers. \
"Amazon's revenue grew 12%" is news, not an insight. "Bezos decides by asking \
which choice he would regret least at 80" is an insight — it names a mechanism \
someone else can use. If a story gives you only a number or an announcement, \
skip it. Four real insights beat six summaries.

ATTRIBUTION IS NOT OPTIONAL. Every insight names the person, their role, and \
where they said it. Never attribute an idea to someone the source does not \
show saying it, and never sharpen a quote into something they did not say. If \
the source only paraphrases, present it as a paraphrase.

Japanese: natural business Japanese, 敬体 (です・ます). Real vocabulary — 意思決定, \
経営判断, 採用, 資本効率, 参入障壁. Not textbook-simplified, not stiff translationese.

Korean: casual-professional (반말 OK), the way you would explain it to a colleague.

CRITICAL TRANSLATION RULE: the Korean under each Japanese paragraph is a FULL \
translation — the SAME NUMBER OF SENTENCES, in the same order, with every name, \
number, qualifier and trailing clause carried across. Count them. Never merge \
two sentences into one and never drop a closing clause because the paragraph \
still reads well without it. A Korean paragraph shorter than the Japanese above \
it is a defect, not economy.

Voice: concrete and useful. No hype, no guru register, no "成功者の習慣" \
listicle tone. Heechang is running a company today — write what changes what \
he does this week.

HEADING TRANSLATION RULE: every 【…】 heading is followed by its Korean \
translation in parentheses.\
"""

ISSUE_PROMPT = """\
Produce today's Business Insight issue from the material below. Today is \
{date_line}.

First line MUST be:
MAIN_TITLE: [concise English title of the single best insight, ≤8 words]

HEADER:
━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS INSIGHT — Issue #{issue_number}
{date_line} · 世界の経営者・投資家に学ぶ、今日のビジネス視点
━━━━━━━━━━━━━━━━━━━━━━━━━━
今日の3つの視点: [2-3 Japanese sentences previewing the three insights]
[the same preview in Korean, starting with 오늘의 세 가지 관점:]

Then FOUR insights, each from a DIFFERENT person. Format each exactly:

━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION {{N}} · 今日のインサイト{{N}} (INSIGHT {{N}})
━━━━━━━━━━━━━━━━━━━━━━━━━━

【Japanese headline naming the idea】(Korean translation of the headline)
📖 語り手: [Name]（[role, company]）· 出典: [where they said it, with the date]

[Japanese: what they actually said or argued. 2-3 sentences, 180-210 \
Japanese characters. Count them.]
📝 한국어 번역:
[full Korean translation, sentence for sentence]

[Japanese: なぜそう言えるのか — the reasoning behind it, or the situation that \
produced it. 2-3 sentences, 180-210 Japanese characters. Count them.]
📝 한국어 번역:
[full Korean translation, sentence for sentence]

[Japanese: どう使うか — how someone running a company would apply this in the \
week ahead. Concrete, but general: address the reader as あなた or write it \
impersonally. Never name a company, and never assume an industry. 2 sentences, \
150-175 Japanese characters — one sentence cannot carry that budget, so write \
two.]
📝 한국어 번역:
[full Korean translation, sentence for sentence]

THREE of the four come from the material below. The FOURTH is a CLASSIC: an \
idea from the past that is not in today's material at all — Bezos on \
minimising regret, Buffett on the circle of competence, Grove on strategic \
inflection points, Christensen on disruption, Drucker on decisions. Use only \
ideas that are genuinely well documented and attributed correctly; if you are \
not certain someone said it, choose a different one. Put it anywhere among the \
four, and mark its 出典 with the original book, talk or letter and its year.

After the four, close the issue:

CLOSING:
━━━━━━━━━━━━━━━━━━━━━━━━━━
Issue #{issue_number} · 明日もまた3つ。
[one-line teaser in Japanese]
[the same teaser in Korean]
━━━━━━━━━━━━━━━━━━━━━━━━━━

LENGTH: 900-1,300 words across both languages. The per-paragraph character \
budgets above are how you get there. The Korean is a full translation and is \
never trimmed to hit this — shorten the Japanese instead.

⚠️ FORMATTING: this displays in Notion as PLAIN TEXT.
- No Markdown at all (no #, ##, **, *, ```)
- ━━━━━━━━━━━━━━━━━━━━ as dividers, before and after each SECTION line
- 【】for the insight headline
- 📖 only for the 語り手 line
- 📝 한국어 번역: before every Korean paragraph
- No other emoji

DO NOT REPEAT these recent issues — pick different people and different ideas:
{recent}

--- MATERIAL FROM THE LAST {lookback} DAYS ---
{news_items}
"""


def generate_issue(items: list[dict], recent: list[str]) -> tuple[str, str]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    now_kst = datetime.now(KST)
    formatted = "\n\n".join(
        f"[{i['source']}] {i['text']}\n  URL: {i['url']}\n  Date: {i['date']}"
        for i in items
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": ISSUE_PROMPT.format(
                issue_number=ISSUE_NUMBER,
                date_line=now_kst.strftime("%B %d, %Y"),
                lookback=LOOKBACK_DAYS,
                recent="\n".join(f"- {t}" for t in recent) or "(none yet)",
                news_items=formatted,
            ),
        }],
    )
    text = resp.content[0].text.strip()

    main_title = "Business Insight"
    lines = text.split("\n")
    if lines and lines[0].startswith("MAIN_TITLE:"):
        main_title = lines[0].replace("MAIN_TITLE:", "").strip()
        text = "\n".join(lines[1:]).strip()
    return main_title, text


def _issue_title(main_title: str) -> str:
    return f"[Business Insight #{ISSUE_NUMBER}] ({main_title})"


# ── Main ────────────────────────────────────────────────────────────────────
def run():
    now_kst = datetime.now(KST)
    print(f"▸ Business Insight — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')}")

    print("▸ Scraping interviews, essays and podcasts...")
    rss_items = scrape_rss_feeds()
    print(f"  Found {len(rss_items)} items.")

    print("▸ Scraping Google News by name...")
    gnews_items = scrape_google_news()
    print(f"  Found {len(gnews_items)} items.")

    all_items = dedupe(rss_items + gnews_items)
    if not all_items:
        print("✗ No material found from any source.")
        sys.exit(1)
    print(f"  {len(all_items)} items after dedupe.")

    recent = store.recent_titles("business", limit=10) if store.configured() else []
    if recent:
        print(f"  Excluding {len(recent)} recent issue(s).")

    print(f"▸ Generating via Claude ({len(all_items[:60])} items)...")
    main_title, issue_text = generate_issue(all_items[:60], recent)
    print(f"  Title: [Business Insight #{ISSUE_NUMBER}] ({main_title})")

    if "--dry-run" in sys.argv:
        print("\n" + "=" * 60)
        print(issue_text)
        print("=" * 60)
        print("\n(dry run — nothing written)")
        return

    blocks = plaintext.to_notion_blocks(issue_text)
    try:
        blocks = furigana.augment(
            blocks,
            variant="sections",
            api_key=ANTHROPIC_API_KEY,
            group_by_story=True,
        )
    except furigana.NoFuriganaTargets as e:
        print(f"  ✗ FURIGANA FOUND NO TARGETS — publishing without it: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ Furigana failed (non-fatal): {e}")

    row = issue_row.build_row(
        section="business",
        issue_date=now_kst.strftime("%Y-%m-%d"),
        raw_title=_issue_title(main_title),
        notion_blocks=blocks,
        source_text=issue_text,
        source_format="plain",
    )

    try:
        n = audio.attach_audio(row["blocks"], "ja")
        print(f"  ✓ Audio: {n} block(s)")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ Audio failed (non-fatal): {e}")

    print("▸ Saving to Supabase...")
    stored = store.upsert_issue(row)
    if stored.get("slug"):
        print(f"✓ Stored: business/{stored['slug']}")
        store.ping_revalidate("business", stored["slug"])

    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
