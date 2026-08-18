"""Chinese sentence → the website's PinyinWord[].

Deterministic on purpose. The obvious alternative — asking Claude to return
hanzi(pinyin) tokens — reintroduces exactly the parse-fragility that
shared/furigana.py's [n]-delimited protocol exists to survive: full-width vs
half-width parentheses, spaces inside a multi-syllable reading, dropped
markers, truncation at max_tokens. It also costs a second 12k-token call and
is non-reproducible, which makes a golden test worthless.

jieba is lossless by construction — "".join(jieba.cut(s)) == s — so a whole
class of failure disappears, and pypinyin consults a phrase dictionary, which
resolves the common 多音字 cases (行 háng/xíng, 长 cháng/zhǎng, 了 le/liǎo)
that a per-character table would get wrong.

annotate() is the seam: swap its body for an LLM pass without touching a
caller, as long as check_lossless() still holds.
"""

from __future__ import annotations

import re

import jieba
from pypinyin import Style, pinyin as _pinyin

# Split punctuation into its own unit here rather than asking a prompt to do it:
# it is mechanical, and doing it in Python removes a class of model error. A unit
# with no reading also renders with no rule under it, which is what the design
# calls for. Full-width and half-width both, plus the CJK quotes and brackets.
_PUNCT = set("，。、；：？！…—‘’“”（）《》〈〉「」『』·,.;:?!()[]\"'")

_HANZI = re.compile(r"[一-鿿㐀-䶿]")

# jieba splits some multi-word organisation names that read as one unit, e.g.
# 国家统计局 → 国家 / 统计局. Grow this list as misses turn up.
ORG_TERMS = (
    "国家统计局", "国务院", "中共中央", "人民银行", "外交部", "商务部",
    "工信部", "发改委", "证监会", "网信办", "国家能源局", "中央政治局",
    "人民日报", "新华社", "全国人大", "政协会议", "国家医保局",
)
for _term in ORG_TERMS:
    jieba.add_word(_term)


def _split_punct(token: str) -> list[str]:
    """Peel punctuation out of a token into standalone units.

    A period or comma between two digits is a decimal or thousands separator,
    not punctuation: splitting 3.5% into 3 / . / 5% made three units where the
    reader sees one number, and put two break opportunities inside it.
    """
    out: list[str] = []
    buf = ""
    for i, ch in enumerate(token):
        if (
            ch in ".,"
            and buf
            and buf[-1].isdigit()
            and i + 1 < len(token)
            and token[i + 1].isdigit()
        ):
            buf += ch
            continue
        if ch in _PUNCT:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


_ORG_SET = frozenset(ORG_TERMS)


def _subwords(unit: str) -> list[str]:
    """Split a token into dictionary sub-words, longest first.

    jieba merges compounds — 科技产业, 保持高速 — into single tokens. Reading
    those as one run ("kējìchǎnyè") is far harder than "kējì chǎnyè", and the
    two-character word is the unit a learner actually looks up.
    """
    if len(unit) <= 2:
        return [unit]
    out: list[str] = []
    i = 0
    while i < len(unit):
        # 3 and 2 only, deliberately not 4: a four-character token is usually
        # itself a dictionary entry (科技产业, 保持高速), so allowing a 4-char
        # match would return it whole — the exact case this splits.
        for size in (3, 2):
            if i + size <= len(unit) and jieba.dt.FREQ.get(unit[i : i + size], 0) > 0:
                out.append(unit[i : i + size])
                i += size
                break
        else:
            out.append(unit[i])
            i += 1
    return out


def _reading(unit: str) -> str:
    """Pinyin for one unit: syllables joined within a word, spaced between."""
    return " ".join(
        "".join(p[0] for p in _pinyin(sub, style=Style.TONE)) for sub in _subwords(unit)
    )


def annotate(sentence: str) -> list[dict]:
    """One Chinese sentence → PinyinWord dicts, ready for a `pinyin` block."""
    words: list[dict] = []
    for token in jieba.cut(sentence.strip(), cut_all=False):
        for chunk in _split_punct(token):
            if not chunk or chunk.isspace():
                continue
            if not _HANZI.search(chunk):
                # Punctuation, Arabic numerals, Latin runs: no reading, and so
                # no rule beneath them.
                words.append({"text": chunk})
                continue
            # Proper nouns stay one unit under one rule; ordinary compounds are
            # split, because 科技 and 产业 are two words a reader looks up
            # separately while 国家统计局 is one name.
            units = [chunk] if chunk in _ORG_SET else _subwords(chunk)
            for unit in units:
                words.append({"text": unit, "pinyin": _reading(unit)})
    return _merge_particles(_merge_measures(words))


# Measure words that follow a numeral and read as one unit with it: 8月, 17日.
# First characters of measure words that follow a numeral. 周 is here for 周年
# (anniversary) and 周 (week); the caller caps the unit at two characters, so
# 年 matches 年/年前 but never 年轻人.
_MEASURES = set("月日年号点分秒岁个次亿万千百元件条张台辆架届期周%")


# Aspect particles read as part of the verb before them rather than as words in
# their own right, and jieba splits them off. 的/地/得 are excluded: they join
# what is around them and stand better alone.
_PARTICLES = {"了": "le", "着": "zhe", "过": "guo"}


def _merge_particles(words: list[dict]) -> list[dict]:
    """Fold an aspect particle into the verb it follows: 影响 + 了 → 影响了."""
    out: list[dict] = []
    for w in words:
        prev = out[-1] if out else None
        if (
            prev
            and w["text"] in _PARTICLES
            and prev.get("pinyin")
            and len(prev["text"]) >= 2
            and _HANZI.search(prev["text"])
        ):
            out[-1] = {
                "text": prev["text"] + w["text"],
                "pinyin": f"{prev['pinyin']} {_PARTICLES[w['text']]}",
            }
            continue
        out.append(w)
    return out


# A digit run, optionally with separators and a percent sign: 100, 1.5, 3,000.
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*%?$")


def _merge_measures(words: list[dict]) -> list[dict]:
    """Fold a bare numeral into the measure word after it.

    A lone "8" carries no reading and so no rule, which left it floating beside
    an underlined 月; and a numeral separated from its unit is also a place the
    line can break, which is how 诞辰100 ended up split from 周年.

    The unit is matched on its FIRST character rather than as a whole string:
    100周年 failed because 周年 is two characters and only single measure chars
    are listed. The two-character cap is what stops it swallowing 年轻人 after a
    digit — 年 is a measure, 年轻人 is not.
    """
    out: list[dict] = []
    for w in words:
        prev = out[-1] if out else None
        if (
            prev
            and "pinyin" not in prev
            and _NUMERAL.match(prev["text"])
            and w.get("pinyin")
            and len(w["text"]) <= 2
            and w["text"][0] in _MEASURES
        ):
            out.pop()
            out.append({"text": prev["text"] + w["text"], "pinyin": w["pinyin"]})
            continue
        out.append(w)
    return out


def check_lossless(sentence: str, words: list[dict]) -> bool:
    """Rejoining the units must reproduce the sentence.

    Cheap, and it is the invariant that makes swapping annotate() for an LLM
    pass safe later — and the gate that keeps a bad segmentation from silently
    dropping half a paragraph.
    """
    return "".join(w["text"] for w in words) == re.sub(r"\s+", "", sentence)
