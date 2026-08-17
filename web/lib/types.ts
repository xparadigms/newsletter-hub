export type SectionKey = "startup" | "fintech" | "japan" | "watch" | "china";

// Compile-time proof that a hand-maintained list covers every section. Several
// of them are ordinary arrays that would happily compile with one missing —
// ORDER in lib/feed.ts being the worst, since a section absent from it vanishes
// from the home page while still appearing in search, the sitemap and its own
// index. Omitting a key here fails the build and names the one you forgot.
export type Covers<T extends readonly SectionKey[]> =
  Exclude<SectionKey, T[number]> extends never
    ? true
    : ["missing SectionKey", Exclude<SectionKey, T[number]>];

export interface Section {
  key: SectionKey;
  number: string;
  label: string;
  title: string;
  description: string;
  // Optional: china is Supabase-only and has no Notion database. Goes away
  // entirely once the Notion mirrors are retired.
  notionId?: string;
}

export interface Post {
  id: string;
  section: SectionKey;
  title: string;
  series: string | null;
  date: string | null;
  summary: string | null;
}

// One unit of a Chinese sentence: a word, a numeral, or a punctuation mark.
// `pinyin` is absent for anything without a reading — punctuation, Arabic
// numerals, Latin runs — which is also what suppresses the rule under it.
//
// Structurally identical to RubySegment in lib/text.ts, and deliberately not
// unified with it: RubySegment is derived at render time by parseRuby, this is
// persisted schema. Sharing one would make this module import that one and
// invert the dependency.
export interface PinyinWord {
  text: string;
  pinyin?: string;
}

export type Block =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; text: string }
  | { type: "callout"; text: string; children: Block[] }
  | { type: "toggle"; text: string; children: Block[] }
  | { type: "code"; text: string; language: string }
  | { type: "image"; url: string; caption: string }
  // Chinese body text, pre-segmented into word units with their readings. The
  // only Block variant Notion cannot produce: china writes Block[] natively
  // rather than through the Notion mapper.
  | { type: "pinyin"; words: PinyinWord[] }
  | { type: "divider" };

export interface PostDetail extends Post {
  blocks: Block[];
}
