import type { SectionKey } from "./types";

// Which half of The Brief the site shows, as in the iOS app (AppMode in
// ios/TheBrief/App/Settings.swift). The Japanese-learning newsletters and the
// Chinese-learning ones are read for different reasons, so each mode keeps to
// its own: Home, Feed, Sections and Explore all follow it. Profile, with your
// saves and history, still shows everything.
//
// The choice lives in a cookie so the server renders the right lists on the
// first request, with no flash of the other mode's issues.

export type Mode = "japan" | "china";

export const MODE_COOKIE = "brief_mode";
export const DEFAULT_MODE: Mode = "japan";

export interface ModeInfo {
  key: Mode;
  title: string;
  flag: string;
  sections: SectionKey[];
  /** The ones with an hourly news feed; Mandarin Basics is a lesson. */
  feedSections: SectionKey[];
}

export const MODES: ModeInfo[] = [
  {
    key: "japan",
    title: "Japan",
    flag: "🇯🇵",
    sections: ["startup", "business", "fintech", "stocks"],
    feedSections: ["startup", "business", "fintech", "stocks"],
  },
  {
    key: "china",
    title: "China",
    flag: "🇨🇳",
    sections: ["china", "mandarin"],
    feedSections: ["china"],
  },
];

export function isMode(value: unknown): value is Mode {
  return value === "japan" || value === "china";
}

export function modeInfo(mode: Mode): ModeInfo {
  return MODES.find((m) => m.key === mode)!;
}
