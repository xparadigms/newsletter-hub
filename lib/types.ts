export type SectionKey = "startup" | "fintech" | "japan" | "watch";

export interface Section {
  key: SectionKey;
  number: string;
  label: string;
  title: string;
  description: string;
  notionId: string;
}

export interface Post {
  id: string;
  section: SectionKey;
  title: string;
  series: string | null;
  date: string | null;
  summary: string | null;
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
  | { type: "divider" };

export interface PostDetail extends Post {
  blocks: Block[];
}
