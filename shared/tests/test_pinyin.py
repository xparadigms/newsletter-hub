"""Golden test for the Chinese segmenter and pinyin readings.

The three sentences are the ones in the design reference, so this pins the
output to the format that was actually signed off — both the unit boundaries
(each unit gets one rule under it) and the readings above them.

It is a golden test at all because annotate() is deterministic. That was the
reason for choosing jieba + pypinyin over a Claude annotation pass: a test
against model output could only ever be tolerant, which makes it weak exactly
where segmentation errors hide.

    python3 shared/tests/test_pinyin.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared import pinyin  # noqa: E402

# (sentence, units, readings) — units are the underlined groups.
GOLDEN = [
    (
        "中国国家统计局于8月17日公布7月经济数据。",
        "中国 国家统计局 于 8月 17日 公布 7月 经济 数据",
        "zhōngguó guójiā tǒngjìjú yú yuè rì gōngbù yuè jīngjì shùjù",
    ),
    (
        "科技产业保持高速增长，但投资大幅下滑，消费依然疲软，整体增长放缓。",
        "科技 产业 保持 高速 增长 但 投资 大幅 下滑 消费 依然 疲软 整体 增长 放缓",
        "kējì chǎnyè bǎochí gāosù zēngzhǎng dàn tóuzī dàfú xiàhuá xiāofèi yīrán "
        "píruǎn zhěngtǐ zēngzhǎng fànghuǎn",
    ),
    (
        "多场台风带来暴雨和洪水，也影响了当月的生产和物流。",
        "多场 台风 带来 暴雨 和 洪水 也 影响了 当月 的 生产 和 物流",
        "duōchǎng táifēng dàilái bàoyǔ hé hóngshuǐ yě yǐngxiǎng le dàngyuè de "
        "shēngchǎn hé wùliú",
    ),
]

# Cases where a naive per-character reading table gets the wrong syllable, or
# where a merge rule could over-reach.
EDGE = [
    # 多音字: the phrase dictionary has to pick háng over xíng in both 银行 and
    # 行长, and zhǎng over cháng in 行长 — a per-character table gets all three
    # wrong.
    ("银行行长表示", "银行 行长 表示", "yínháng hángzhǎng biǎoshì"),
    # 了 as part of a verb, then as an aspect particle — both in one sentence.
    ("他了解了情况", "他 了解了 情况", None),
    # 的 is not an aspect particle and must stay its own unit.
    ("中国的经济", "中国 的 经济", None),
]

failures: list[str] = []


def check(name: str, actual, wanted) -> None:
    if actual == wanted:
        print(f"ok   {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}\n       wanted: {wanted}\n       actual: {actual}")


for sentence, units, readings in GOLDEN:
    words = pinyin.annotate(sentence)
    check(f"lossless: {sentence[:16]}…", pinyin.check_lossless(sentence, words), True)
    check(
        f"units:    {sentence[:16]}…",
        " ".join(w["text"] for w in words if w.get("pinyin")),
        units,
    )
    check(
        f"readings: {sentence[:16]}…",
        " ".join(w["pinyin"] for w in words if w.get("pinyin")),
        readings,
    )

for sentence, units, readings in EDGE:
    words = pinyin.annotate(sentence)
    check(f"edge units:    {sentence}", " ".join(w["text"] for w in words if w.get("pinyin")), units)
    if readings is not None:
        check(
            f"edge readings: {sentence}",
            " ".join(w["pinyin"] for w in words if w.get("pinyin")),
            readings,
        )

# Punctuation must survive as its own unreadable unit, or the rule under the
# preceding word would run into it.
words = pinyin.annotate("增长，放缓。")
check("punctuation kept, unread", [w["text"] for w in words if "pinyin" not in w], ["，", "。"])

print("\nPASS" if not failures else f"\nFAIL ({len(failures)})")
raise SystemExit(1 if failures else 0)
