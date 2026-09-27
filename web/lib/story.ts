import type { AnnotatedBlock, RubySegment } from "./text";
import type { PostDetail, Section } from "./types";

// An issue becomes a deck of full-screen cards. Issues are already written as
// "section heading → story heading → what happened → translations", so each
// heading starts a new card and the blocks under it become that card's body.

export interface CoverCard {
  kind: "cover";
  sectionLabel: string;
  sectionNumber: string;
  series: string | null;
  title: string;
  summary: string | null;
  date: string | null;
  minutes: number;
  count: number;
}

export interface SectionCard {
  kind: "section";
  heading: string;
  index: number;
  total: number;
}

export interface ContentCard {
  kind: "content";
  heading: string | null;
  // Korean rendering of the heading, where the issue supplies one as its own
  // paragraph. It belongs with the heading, not in the pairing pool.
  subtitle: string | null;
  kicker: string | null;
  blocks: AnnotatedBlock[];
}

export type StoryCard = CoverCard | SectionCard | ContentCard;

// ── Three Companies ────────────────────────────────────────────────────────
// A stock article is four parts under 【】 headings. Basic info is a run of
// bullets that belongs on one card. The other parts are long paragraphs, and
// a card holding a whole one needed scrolling on a phone, so they are cut into
// cards of whole sentences, each card's Japanese followed by its Korean.

// Roughly what fits on a phone card before it reads as a wall of text.
const STOCK_CARD_LINES = 7;
// Full-width characters per line on a 390px phone at the story card's body
// sizes: 19px Japanese, and Korean, whose glyphs set a little narrower.
const LINE_CAPACITY = { ja: 17, ko: 20 } as const;

/** Estimated rendered lines. Latin letters, digits and spaces are about half
 *  the width of a full-width character. */
function estimateLines(text: string, lang: "ja" | "ko"): number {
  let units = 0;
  for (const ch of text) {
    units += /[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7a3\uff00-\uffef]/.test(ch) ? 1 : 0.55;
  }
  return Math.max(1, Math.ceil(units / LINE_CAPACITY[lang]));
}

// Japanese sentences end at 。！？, with any closing bracket that follows.
const JA_SENTENCE = /[^。！？]*[。！？]+[」』）)]*|[^。！？]+$/g;

function splitJa(text: string): string[] {
  return (text.match(JA_SENTENCE) ?? []).map((t) => t.trim()).filter(Boolean);
}

/** Korean sentences end at . ! ? before a space or the end. Not after a Latin
 *  letter, so "Nu Holdings Ltd. 는" stays one sentence, and never inside a
 *  number like 13.59, where no space follows. */
function splitKo(text: string): string[] {
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (".!?".includes(ch) && (i + 1 === text.length || /\s/.test(text[i + 1]))) {
      if (ch === "." && /[A-Za-z]/.test(text[i - 1] ?? "")) continue;
      out.push(text.slice(start, i + 1).trim());
      start = i + 1;
    }
  }
  if (text.slice(start).trim()) out.push(text.slice(start).trim());
  return out.filter(Boolean);
}

/** Cut ruby segments into sentences at the same 。！？ marks as splitJa.
 *  Readings sit on words, never on punctuation, so a sentence end is always
 *  inside an unread segment. */
function splitRuby(segments: RubySegment[]): RubySegment[][] {
  const out: RubySegment[][] = [];
  let current: RubySegment[] = [];
  for (const seg of segments) {
    if (seg.reading) {
      current.push(seg);
      continue;
    }
    for (const piece of seg.text.match(JA_SENTENCE) ?? [seg.text]) {
      current.push({ text: piece });
      if (/[。！？][」』）)]*$/.test(piece)) {
        out.push(current);
        current = [];
      }
    }
  }
  if (current.some((seg) => seg.text.trim())) out.push(current);
  return out;
}

interface SentencePair {
  ja: AnnotatedBlock[];
  ko: AnnotatedBlock[];
}

/** One Japanese paragraph and its Korean translation as sentence pairs. The
 *  Korean is written sentence for sentence; where the counts still differ,
 *  each Korean sentence goes with the Japanese one at the same relative
 *  position, so nothing is dropped and nothing moves ahead of its source. */
function sentencePairs(ja: AnnotatedBlock, ko: AnnotatedBlock | undefined): SentencePair[] {
  const text = ja.block.type === "paragraph" ? ja.block.text : "";
  const jaTexts = splitJa(text);
  const rubies = ja.ruby ? splitRuby(ja.ruby) : null;
  // Readings that do not cut into the same sentences stay whole: a paragraph
  // on one card with its furigana beats sentences without it.
  if (jaTexts.length < 2 || (rubies && rubies.length !== jaTexts.length)) {
    return [{ ja: [ja], ko: ko ? [ko] : [] }];
  }
  const pairs: SentencePair[] = jaTexts.map((t, i) => ({
    ja: [
      {
        ...ja,
        block: { type: "paragraph", text: t, ...(i === 0 && ja.block.type === "paragraph" && ja.block.audio ? { audio: ja.block.audio } : {}) },
        ruby: rubies ? rubies[i] : undefined,
      },
    ],
    ko: [],
  }));
  const koTexts = ko && ko.block.type === "paragraph" ? splitKo(ko.block.text) : [];
  koTexts.forEach((t, j) => {
    const i = Math.min(jaTexts.length - 1, Math.floor((j * jaTexts.length) / koTexts.length));
    pairs[i].ko.push({ ...ko!, block: { type: "paragraph", text: t } });
  });
  return pairs;
}

function stockCards(
  heading: string,
  blocks: AnnotatedBlock[],
  subtitle: string | null,
  kicker: string | null
): ContentCard[] {
  const card = (b: AnnotatedBlock[]): ContentCard => ({
    kind: "content",
    heading,
    subtitle,
    kicker,
    blocks: b,
  });
  const body = blocks.filter((a) => a.block.type !== "divider");
  if (!body.length) return [];
  // Basic info, and the source links, are one card however long.
  if (heading.includes("基本情報") || body.every((a) => a.lang === null)) {
    return [card(body)];
  }

  // Japanese paragraphs each followed by their Korean, in source order.
  const pairs: SentencePair[] = [];
  const rest: AnnotatedBlock[] = [];
  for (let i = 0; i < body.length; i++) {
    const a = body[i];
    if (a.lang === "ja" && a.block.type === "paragraph") {
      const next = body[i + 1];
      const ko = next?.lang === "ko" && next.block.type === "paragraph" ? next : undefined;
      pairs.push(...sentencePairs(a, ko));
      if (ko) i++;
    } else {
      rest.push(a);
    }
  }
  if (!pairs.length) return [card(body)];

  const lines = (p: SentencePair) =>
    p.ja.reduce((n, a) => n + estimateLines(a.block.type === "paragraph" ? a.block.text : "", "ja"), 0) +
    p.ko.reduce((n, a) => n + estimateLines(a.block.type === "paragraph" ? a.block.text : "", "ko"), 0);

  // Greedy: a sentence pair joins the card unless it would push it past the
  // budget. A single pair over budget still gets a card of its own; sentences
  // are never cut.
  const cards: ContentCard[] = [];
  let group: SentencePair[] = [];
  let used = 0;
  const flush = () => {
    if (!group.length) return;
    // Japanese first, then its Korean, the way the article reads.
    cards.push(card([...group.flatMap((p) => p.ja), ...group.flatMap((p) => p.ko)]));
    group = [];
    used = 0;
  };
  for (const p of pairs) {
    const n = lines(p);
    if (group.length && used + n > STOCK_CARD_LINES) flush();
    group.push(p);
    used += n;
  }
  flush();
  if (rest.length) cards[cards.length - 1].blocks.push(...rest);
  return cards;
}

function formatDate(date: string | null): string | null {
  if (!date) return null;
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function buildDeck(
  annotated: AnnotatedBlock[],
  post: PostDetail,
  section: Section,
  minutes: number
): StoryCard[] {
  const cards: StoryCard[] = [];

  // Group blocks under the heading that introduces them.
  interface Group {
    heading: string | null;
    subtitle: string | null;
    level: number;
    kicker: string | null;
    blocks: AnnotatedBlock[];
  }
  const groups: Group[] = [];
  let current: Group | null = null;

  for (const a of annotated) {
    // Images carry expiring Notion URLs; dividers are kept because they mark
    // the boundary between translation units inside a story.
    if (a.block.type === "image") continue;

    if (a.block.type === "heading") {
      current = {
        heading: a.block.text.trim(),
        subtitle: null,
        level: a.block.level,
        kicker: null,
        blocks: [],
      };
      groups.push(current);
      continue;
    }
    if (!current) continue; // front matter before the first heading

    if (a.kicker && a.block.type === "paragraph") {
      // "WHAT HAPPENED" etc. labels the card rather than filling it.
      if (!current.kicker) current.kicker = a.block.text.trim();
      continue;
    }
    // A Korean paragraph before any Japanese one cannot be a translation of a
    // Japanese paragraph that hasn't appeared yet — it is the heading rendered
    // in Korean. Leaving it in the pool shifted every pairing by one, so the
    // Japanese body was matched with the heading and its real translation was
    // orphaned onto the next card.
    if (
      a.lang === "ko" &&
      a.block.type === "paragraph" &&
      !current.subtitle &&
      !current.blocks.some((b) => b.lang === "ja" || b.lang === "zh")
    ) {
      current.subtitle = a.block.text.trim();
      continue;
    }

    current.blocks.push(a);
  }

  // A section heading (h3) with no body of its own becomes a divider card;
  // anything with content becomes a content card.
  const sectionHeads = groups.filter((g) => g.level <= 2 && !g.blocks.length);
  let sectionSeen = 0;

  for (const g of groups) {
    if (g.level <= 2 && !g.blocks.length) {
      sectionSeen += 1;
      cards.push({
        kind: "section",
        heading: g.heading ?? "",
        index: sectionSeen,
        total: sectionHeads.length,
      });
      continue;
    }
    if (!g.blocks.length) continue;

    if (section.key === "stocks") {
      cards.push(...stockCards(g.heading ?? "", g.blocks, g.subtitle, g.kicker));
      continue;
    }

    // China and Mandarin Basics number their headings — "1. …", "2. …" — and
    // each number is one news story or one lesson step. Splitting it into a
    // card per sentence scattered one item across several cards under the same
    // number, so it stays whole on a single card in source order, and the card
    // body scrolls if it runs long.
    if (section.sourceLang === "zh") {
      const blocks = g.blocks.filter((a) => a.block.type !== "divider");
      if (blocks.length) {
        cards.push({
          kind: "content",
          heading: g.heading,
          subtitle: g.subtitle,
          kicker: g.kicker,
          blocks,
        });
      }
      continue;
    }

    // One translation pair per card. A story previously became a single card
    // holding every paragraph in all three languages, which overflowed the
    // screen.
    const isLabelCallout = (a: AnnotatedBlock) =>
      a.block.type === "callout" && /^日本語/.test(a.block.text.trim());

    // Issues separate their translation units with dividers, so those are the
    // natural card boundaries.
    //
    // The Sweep has none: under one region heading it runs headline, bullets,
    // Japanese, Korean, then straight into the next headline. Everything landed
    // in a single chunk and was paired by position ACROSS stories, so a card
    // showed one story's Japanese beside another's Korean. An English paragraph
    // arriving after Korean can only be the next unit starting, so it opens a
    // chunk too.
    const chunks: AnnotatedBlock[][] = [[]];
    for (const a of g.blocks) {
      if (a.block.type === "divider") {
        if (chunks[chunks.length - 1].length) chunks.push([]);
        continue;
      }
      if (isLabelCallout(a)) continue; // the language is self-evident on a card
      const chunk = chunks[chunks.length - 1];
      // Paragraph or list: the Sweep leads each unit with an English headline
      // paragraph, while startup's "Other Notable Headlines" leads with an
      // English list. Both are the same signal.
      const isEnglishLead =
        (a.block.type === "paragraph" || a.block.type === "list") &&
        a.lang !== "ja" &&
        a.lang !== "zh" &&
        a.lang !== "ko";
      if (isEnglishLead && chunk.some((b) => b.lang === "ko")) {
        chunks.push([a]);
        continue;
      }
      chunk.push(a);
    }

    for (const chunk of chunks) {
      const ja = chunk.filter((a) => a.lang === "ja");
      const zh = chunk.filter((a) => a.lang === "zh");
      const ko = chunk.filter((a) => a.lang === "ko");
      // Still defined negatively so lang-null leftovers land here as before;
      // adding "zh" to the exclusion is the fix. Without it Chinese body text
      // was bucketed as English filler and spread across cards, and a
      // Chinese-only chunk gave pairs === 0 and was dropped outright.
      const en = chunk.filter(
        (a) => a.lang !== "ja" && a.lang !== "zh" && a.lang !== "ko"
      );

      // A bulleted unit is a headline plus the bullets belonging to it, and
      // notion_blocks_to_web has already merged each run of bullets into ONE
      // list block. The counts per language therefore do not line up — three
      // Japanese blocks against two Korean ones — and pairing split the
      // headline away from its own bullets, dropping whichever had no
      // counterpart. Keep the unit whole.
      if (chunk.some((a) => a.block.type === "list")) {
        cards.push({
          kind: "content",
          heading: g.heading,
          subtitle: g.subtitle,
          kicker: g.kicker,
          blocks: [...chunk],
        });
        continue;
      }

      // China writes one Korean read-through per story rather than one per
      // sentence, so there is nothing to pair positionally: pairing put the
      // translation after the first Chinese line and folded the rest in behind
      // it, leaving Korean stranded in the middle. Keep the source order.
      const source = ja.length ? ja : zh;
      if (ko.length === 1 && source.length > 1) {
        cards.push({
          kind: "content",
          heading: g.heading,
          subtitle: g.subtitle,
          kicker: g.kicker,
          blocks: [...chunk],
        });
        continue;
      }

      // Where a chunk holds several paragraphs per language — news briefs list
      // all the Japanese then all the Korean, dialogues interleave them —
      // pairing by position lines the translations up either way.
      const pairs = Math.max(ja.length, zh.length, ko.length);

      if (pairs === 0) {
        if (!en.length) continue;
        // English-only remainder: fold it into the previous card rather than
        // making a card that would be blank in the default Japanese/Korean view.
        const last = cards[cards.length - 1];
        if (last?.kind === "content") last.blocks.push(...en);
        continue;
      }

      // English usually runs a label plus a body per unit, so it outnumbers the
      // other languages. Spread it across the chunk's cards instead of piling
      // every block onto the first one.
      const enPerCard = Math.ceil(en.length / pairs);

      for (let i = 0; i < pairs; i++) {
        const pair = [ja[i], zh[i], ko[i]].filter(Boolean) as AnnotatedBlock[];
        if (!pair.length) continue;

        // A block with no counterpart — a Korean-only "왜 중요한가" note, say —
        // joins the card before it rather than sitting alone on its own.
        const previous = cards[cards.length - 1];
        if (pair.length === 1 && i > 0 && previous?.kind === "content") {
          previous.blocks.push(...pair);
          continue;
        }

        cards.push({
          // The heading rides along on every card of a story so a reader
          // landing mid-story still knows what it is about.
          kind: "content",
          heading: g.heading,
          subtitle: g.subtitle,
          kicker: g.kicker,
          blocks: [...en.slice(i * enPerCard, (i + 1) * enPerCard), ...pair],
        });
      }
    }
  }

  const cover: CoverCard = {
    kind: "cover",
    sectionLabel: section.label,
    sectionNumber: section.number,
    series: post.series,
    title: post.title,
    summary: post.summary,
    date: formatDate(post.date),
    minutes,
    // Matches the counter in the viewer: cover + cards.
    count: cards.length + 1,
  };

  return [cover, ...cards];
}
