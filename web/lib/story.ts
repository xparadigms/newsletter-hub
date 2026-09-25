import type { AnnotatedBlock } from "./text";
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
