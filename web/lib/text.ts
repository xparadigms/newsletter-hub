import type { Block } from "./types";

export type Lang = "en" | "ja" | "ko";

export interface RubySegment {
  text: string;
  reading?: string;
}

export interface AnnotatedBlock {
  block: Block;
  // null = structural (headings, kickers, dividers, images) — always visible
  lang: Lang | null;
  kicker: boolean;
  // Set when a ふりがな toggle supplied readings for this paragraph.
  ruby?: RubySegment[];
  // Anchor target for the table of contents (headings only).
  headingId?: string;
}

export interface TocItem {
  id: string;
  text: string;
  level: number;
}

// The index suffix keeps ids unique even when two sections share a title.
function slugify(text: string, index: number): string {
  const base = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return base ? `${base}-${index}` : `section-${index}`;
}

export function buildToc(annotated: AnnotatedBlock[]): TocItem[] {
  const items: TocItem[] = [];
  for (const a of annotated) {
    if (a.block.type === "heading" && a.headingId && a.block.text.trim()) {
      items.push({
        id: a.headingId,
        text: a.block.text.trim(),
        level: a.block.level,
      });
    }
  }
  return items;
}

// Furigana arrives as 漢字（かんじ）: a run followed by its reading in full-width
// parentheses. The base can also be a Latin/number token — issues gloss loan
// words too, e.g. Circle（サークル） — and the reading can be katakana. Missing
// those made the annotated sentence differ from the plain one, so it failed the
// duplicate check below and rendered as a second copy of the same paragraph.
const rubyPattern = () =>
  /([\u4E00-\u9FFF\u3400-\u4DBF\u3005\u3006\u30F6]+|[A-Za-z0-9]+)\uFF08([\u3040-\u30FF\u30FC]+)\uFF09/g;

export function parseRuby(text: string): RubySegment[] {
  const out: RubySegment[] = [];
  let last = 0;
  for (const m of text.matchAll(rubyPattern())) {
    const i = m.index ?? 0;
    if (i > last) out.push({ text: text.slice(last, i) });
    out.push({ text: m[1], reading: m[2] });
    last = i + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

export function stripFurigana(text: string): string {
  return text.replace(rubyPattern(), "$1");
}

function normalize(text: string): string {
  return text.replace(/\s+/g, "");
}

// The sentence a furigana toggle annotates, whether it was written as a
// paragraph or as a bullet.
function plainText(block: Block): string {
  if (block.type === "paragraph") return block.text;
  if (block.type === "list") return block.items.join("");
  return "";
}

// ALL-CAPS short paragraphs act as section kickers in the newsletter bodies
// ("WHAT HAPPENED", "SECTION 1 — THREE DEEP READS").
// Guard against CJK: Korean/Japanese prose whose only Latin is an uppercase
// acronym ("ASA 관점에서...") would otherwise look like an English kicker.
export function isKicker(text: string): boolean {
  const t = text.trim();
  return (
    t.length >= 3 &&
    t.length <= 80 &&
    /[A-Z]{2}/.test(t) &&
    !/[a-z]/.test(t) &&
    !/[\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]/.test(t)
  );
}

function scriptCounts(text: string) {
  const count = (re: RegExp) => (text.match(re) ?? []).length;
  return {
    hangul: count(/[\uAC00-\uD7A3]/g),
    kana: count(/[\u3040-\u30FF]/g),
    han: count(/[\u4E00-\u9FFF\u3400-\u4DBF]/g),
    latin: count(/[A-Za-z]/g),
  };
}

export function classifyLang(text: string): Lang {
  const { hangul, kana, han, latin } = scriptCounts(text);
  // Floor of 3 keeps single quoted foreign words inside English prose "en";
  // "kana + han > latin" keeps English sentences citing a Japanese term "en".
  if (hangul >= 3 && hangul > kana) return "ko";
  if (kana > 0 && kana + han > latin) return "ja";
  // Kanji-only lines: no Chinese content exists in these newsletters.
  if (kana === 0 && han >= 3 && han > latin) return "ja";
  return "en";
}

export function blockText(block: Block): string {
  switch (block.type) {
    case "paragraph":
    case "heading":
    case "quote":
    case "code":
      return block.text;
    case "list":
      return block.items.join(" ");
    case "pinyin":
      // Without this the block flattens to "" and classifies as English, which
      // hides the entire Chinese body in the default reading view.
      return block.words.map((w) => w.text).join("");
    case "callout":
    case "toggle":
      return [block.text, ...block.children.map(blockText)].join(" ");
    default:
      return "";
  }
}

// Characters of shared opening that identify two renderings of one sentence.
const PREFIX_MATCH = 12;

// The remainder of `text` after `count` non-whitespace characters.
function sliceAfterNormalized(text: string, count: number): string {
  let seen = 0;
  let i = 0;
  while (i < text.length && seen < count) {
    if (!/\s/.test(text[i])) seen += 1;
    i += 1;
  }
  return text.slice(i);
}

// Split one furigana string back across several paragraphs, given the plain
// length each paragraph should receive.
function splitRubyAcross(furigana: string, sizes: number[]): RubySegment[][] {
  const segments = parseRuby(furigana);
  const buckets: RubySegment[][] = sizes.map(() => []);
  let bi = 0;
  let filled = 0;

  const advance = () => {
    while (bi < sizes.length && filled >= sizes[bi]) {
      filled -= sizes[bi];
      bi += 1;
    }
  };

  for (const seg of segments) {
    if (seg.reading) {
      // A ruby unit belongs to whichever paragraph it started in.
      buckets[Math.min(bi, buckets.length - 1)].push(seg);
      filled += normalize(seg.text).length;
      advance();
      continue;
    }
    let text = seg.text;
    while (text.length > 0) {
      if (bi >= sizes.length) {
        buckets[buckets.length - 1].push({ text });
        break;
      }
      const remain = sizes[bi] - filled;
      let take = 0;
      let counted = 0;
      while (take < text.length && counted < remain) {
        if (!/\s/.test(text[take])) counted += 1;
        take += 1;
      }
      while (take < text.length && /\s/.test(text[take])) take += 1;
      buckets[bi].push({ text: text.slice(0, take) });
      filled += counted;
      text = text.slice(take);
      advance();
    }
  }
  return buckets;
}

// A ふりがな toggle repeats what came before it, with readings attached. That
// may be one paragraph, a bullet, or — in the dialogue sections — every
// Japanese turn concatenated into a single block, placed after the Korean.
// Attach the readings to whichever run of earlier Japanese blocks it
// reproduces, so the annotated copy never renders as a second, combined
// paragraph.
function attachFurigana(out: AnnotatedBlock[], furigana: string): boolean {
  const plain = normalize(stripFurigana(furigana));
  if (!plain) return false;

  // Every Japanese block since the last heading that has no readings yet.
  // Korean turns and the 日本語 label may sit between them and the toggle.
  const run: AnnotatedBlock[] = [];
  for (let i = out.length - 1; i >= 0; i--) {
    const a = out[i];
    if (a.block.type === "heading") break;
    if (
      (a.block.type === "paragraph" || a.block.type === "list") &&
      a.lang === "ja" &&
      !a.ruby
    ) {
      run.unshift(a);
    }
  }

  for (const a of run) {
    const written = plainText(a.block);
    const nWritten = normalize(written);
    if (!nWritten) continue;

    // Same sentence, verbatim.
    if (nWritten === plain) {
      a.ruby = parseRuby(furigana);
      return true;
    }
    // The written sentence often ends with a source citation the annotated
    // version omits; keep that tail rather than dropping it.
    if (nWritten.startsWith(plain) && plain.length >= nWritten.length * 0.6) {
      const segments = parseRuby(furigana);
      const tail = sliceAfterNormalized(written, plain.length);
      if (tail) segments.push({ text: tail });
      a.ruby = segments;
      return true;
    }
    // Some sentences embed the citation mid-way — "…されたんだ（KSI政策ニュース,
    // …）" — where the annotated rewrite runs straight on, so neither equality
    // nor a prefix lines up. A shared opening identifies the same sentence.
    if (
      nWritten.length >= PREFIX_MATCH &&
      plain.length >= PREFIX_MATCH &&
      nWritten.slice(0, PREFIX_MATCH) === plain.slice(0, PREFIX_MATCH)
    ) {
      a.ruby = parseRuby(furigana);
      return true;
    }
  }

  // Or one child covering a run of consecutive blocks.
  for (let k = 2; k <= run.length; k++) {
    for (let from = 0; from + k <= run.length; from++) {
      const slice = run.slice(from, from + k);
      const sizes = slice.map((a) => normalize(plainText(a.block)).length);
      if (sizes.reduce((n, x) => n + x, 0) === 0) continue;
      if (slice.map((a) => normalize(plainText(a.block))).join("") !== plain) continue;
      const parts = splitRubyAcross(furigana, sizes);
      slice.forEach((a, i) => {
        if (parts[i]?.length) a.ruby = parts[i];
      });
      return true;
    }
  }
  return false;
}

export function annotateBlocks(blocks: Block[]): AnnotatedBlock[] {
  const out: AnnotatedBlock[] = [];
  let prev: Lang | null = null;

  // Issues open with decorative dividers; they'd render as empty rules under
  // the deck.
  let start = 0;
  while (start < blocks.length && blocks[start].type === "divider") start++;

  for (const block of blocks.slice(start)) {
    if (block.type === "divider" || block.type === "image") {
      out.push({ block, lang: null, kicker: false });
      continue;
    }
    // Headings anchor the issue's structure; keep them visible in every mode.
    if (block.type === "heading") {
      out.push({
        block,
        lang: null,
        kicker: false,
        headingId: slugify(block.text, out.length),
      });
      continue;
    }

    let lang: Lang;
    const label = block.type === "callout" || block.type === "toggle" ? block.text.trim() : "";
    if (block.type === "callout" && /^日本語/.test(label) && label.length <= 12) {
      // Bare "日本語" callouts are labels for the Japanese paragraphs that follow.
      lang = "ja";
    } else if (block.type === "toggle" && /ふりがな|ひらがな/.test(label)) {
      // Each child annotates one earlier block, so they are matched one by one
      // rather than joined. Joining them is what produced the combined
      // transliterated paragraph under the dialogue sections.
      const parts = block.children
        .filter((c) => c.type === "paragraph")
        .map((c) => (c as { text: string }).text)
        .filter((t) => t.trim().length > 0);
      if (parts.length > 0) {
        for (const part of parts) {
          if (attachFurigana(out, part)) continue;
          // Genuinely new annotated content (説明 / 示唆): keep it as its own
          // paragraph rather than hiding it behind a toggle.
          out.push({
            block: { type: "paragraph", text: stripFurigana(part) },
            lang: "ja",
            kicker: false,
            ruby: parseRuby(part),
          });
          prev = "ja";
        }
        continue;
      }
      lang = "ja";
    } else {
      const text = blockText(block);
      lang = classifyLang(text);
      if (lang === "en" && prev === "ja") {
        // Short kanji-only fragments between Japanese paragraphs stay Japanese.
        const c = scriptCounts(text);
        if (c.kana === 0 && c.latin === 0 && c.han > 0) lang = "ja";
      }
    }
    // Kickers are the English structural skeleton ("WHAT HAPPENED"), so only
    // blocks that classified as English qualify.
    const kicker =
      block.type === "paragraph" && lang === "en" && isKicker(block.text);
    // Kickers label the section rather than carry prose, so they stay visible
    // alongside whichever language the reader has chosen.
    out.push({ block, lang: kicker ? null : lang, kicker });
    prev = lang;
  }
  return out;
}

// English-only word count keeps the estimate honest regardless of the reader's
// translation-filter setting.
export function readingTime(annotated: AnnotatedBlock[]): number {
  let words = 0;
  for (const a of annotated) {
    if (a.lang === "en") {
      words += blockText(a.block).split(/\s+/).filter(Boolean).length;
    }
  }
  return Math.max(1, Math.round(words / 230));
}
