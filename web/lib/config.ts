import type { Covers, Section, SectionKey } from "./types";

export const SITE = {
  name: "The Brief",
  url: "https://heechang-newsletter.vercel.app",
  tagline: "Daily newsletters by Heechang",
  description:
    "Daily briefs on startups, financial infrastructure, Japan's crypto market, China, and the watch world — written for people who want the signal without the feed.",
};

// Each section is backed by one Notion database. IDs come from the shared
// Notion URLs; override with env vars if the databases move.
export const SECTIONS: Section[] = [
  {
    key: "startup",
    number: "01",
    label: "Startup",
    title: "Startup News",
    description:
      "Funding rounds, acquisitions, and the moves that matter across the startup landscape.",
    notionId:
      process.env.NOTION_DB_STARTUP ?? "3555bc953df380e2ae70df4401216aee",
  },
  {
    key: "fintech",
    number: "02",
    label: "Fintech",
    title: "Finance Infra",
    description:
      "A daily journal on the future of financial infrastructure — stablecoins, settlement rails, and tokenized money.",
    notionId:
      process.env.NOTION_DB_FINTECH ?? "3535bc953df3807b83c9dc5be40b72e6",
  },
  {
    key: "japan",
    number: "03",
    label: "Japan",
    title: "Japan Brief",
    description:
      "Regulation, institutions, and market structure in Japan's digital asset market.",
    notionId: process.env.NOTION_DB_JAPAN ?? "36a5bc953df38036acb4d2b6553e582c",
  },
  {
    key: "watch",
    number: "04",
    label: "Watch",
    title: "Watch Weekly",
    description:
      "A weekly read on the watch world — auctions, releases, and the market behind them.",
    notionId: process.env.NOTION_DB_WATCH ?? "3965bc953df381bbb5ece93744153a6a",
  },
  {
    key: "china",
    number: "05",
    label: "China",
    title: "China Daily",
    description:
      "Politics, technology, and what China is actually talking about — short Chinese paragraphs with pinyin and a Korean read-through.",
    // No notionId: china is Supabase-only and has no Notion database.
  },
];

// Fails the build, naming the offender, if a section is missing from SECTIONS.
const SECTION_KEYS = SECTIONS.map((s) => s.key) as [
  "startup",
  "fintech",
  "japan",
  "watch",
  "china",
];
const _sectionsCover: Covers<typeof SECTION_KEYS> = true;
void _sectionsCover;

export function getSection(key: string): Section | undefined {
  return SECTIONS.find((s) => s.key === key);
}

export function sectionKeys(): SectionKey[] {
  return SECTIONS.map((s) => s.key);
}
