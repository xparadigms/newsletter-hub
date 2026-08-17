# Trilingual Startup Newsletter — Formatting Spec

## Overview
Convert each English startup newsletter into a trilingual (English + Japanese + Korean) edition, formatted in Notion-flavored Markdown. Apply to every story/section.

---

## Per-Story Structure

For each story, output in this order:

```
### 【日本語の見出し】
(한국어 부제목 — Korean subtitle)
*English headline*
```

Then for each sub-section (▸ What happened / ▸ Industry status / ▸ Why this is disruptive, etc.):

Keep the English bullet/label, then under each:

1. **English paragraph** — unchanged from source
2. **Japanese translation** of that paragraph
3. **Furigana toggle** (collapsible):
   ```
   <details>
   <summary>ふりがな（ひらがな）</summary>
   	[furigana version of the Japanese paragraph]
   </details>
   ```
4. **Korean callout + translation**:
   ```
   <callout icon="📝">
   	한국어 번역
   </callout>
   [Korean translation of that paragraph]
   ```

Then add a takeaway line:
```
왜 중요한가: [1–2 sentences in Korean on why this matters for a startup/tech/investor reader]
```

---

## Furigana Rules (Furigana Style, NOT Full Hiragana)

1. Keep all kanji in place; add the reading in parentheses immediately after each kanji word.
   - e.g. 暗号資産（あんごうしさん）, 評価額（ひょうかがく）, 求（もと）める
2. Leave katakana, numbers, Latin letters (Supabase, AWS, $10B), and punctuation unchanged.
3. Preserve any readings already shown in the original.
4. Handle okurigana correctly — e.g. 円建（えんだ）て, 基（もと）づく.
5. Furigana text inside the toggle must be indented one tab so it stays inside the toggle.

---

## Formatting Rules

- Do NOT add furigana to headings, section titles, or 【...】 lines.
- Do NOT touch the Korean text, callouts, dividers, or other formatting.
- Translate currency/units naturally:
  - e.g. $10B → 100億ドル (JP) / 100억 달러 (KR)
  - Keep the English figure in the English layer.
- Keep section dividers (`---`) between stories.
- **"OTHER NOTABLE HEADLINES"-type bullet lists:**
  Each bullet as English line → Japanese (with inline furigana) → Korean. No toggle needed for single-line headlines.

---

## Closing Section: 今週の表現 / 今週の単語

At the end of each issue, pick one useful Japanese business/tech term from the issue:

```
## 今週の表現 / 이번 주 표현

**[term]**
- 読み方: [reading]
- 意味: [Korean meaning]
- 例文: [example sentence in Japanese]

<details>
<summary>ふりがな</summary>
	[furigana version of the example sentence]
</details>

- メモ: [one-line note on usage]
```

---

## Tone

- **Japanese:** Clean, journalistic newsletter tone (です/ます or だ/である — match the source register).
- **Korean:** Natural, concise translation aimed at a startup/crypto-savvy reader.
