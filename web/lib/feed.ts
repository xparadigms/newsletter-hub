import type { Covers, Post, SectionKey } from "./types";

// Fixed tie-break order for same-day posts in the merged feed (dates are
// date-only, so daily newsletters collide constantly).
// `as const`, not SectionKey[]: with a widened element type, omitting a section
// compiles fine and that section silently disappears from the home page — while
// still appearing in its own index, in search and in the sitemap. The guard
// below turns that into a build failure.
const ORDER = ["startup", "business", "stocks", "fintech", "japan", "china", "mandarin", "watch"] as const;
const _orderCovers: Covers<typeof ORDER> = true;
void _orderCovers;

export function flattenLatest(
  posts: Record<SectionKey, Post[]>,
  limit: number
): Post[] {
  const all = ORDER.flatMap((key) => posts[key]);
  all.sort((a, b) => {
    const byDate = (b.date ?? "").localeCompare(a.date ?? "");
    if (byDate !== 0) return byDate;
    return ORDER.indexOf(a.section) - ORDER.indexOf(b.section);
  });
  return all.slice(0, limit);
}

// The front page always leads with the newest issue. It used to prefer the
// newest issue that had a Summary, which silently demoted a same-day issue
// published without one below an older issue. A missing Summary just means the
// lead renders without a deck.
export function pickLead(latest: Post[]): Post | null {
  return latest[0] ?? null;
}

// posts are sorted date-descending: "next" is the newer neighbor.
export function findAdjacent(
  posts: Post[],
  id: string
): { prev: Post | null; next: Post | null } {
  const i = posts.findIndex((p) => p.id === id);
  if (i === -1) return { prev: null, next: null };
  return { next: posts[i - 1] ?? null, prev: posts[i + 1] ?? null };
}

export function groupByMonth(posts: Post[]): { month: string; posts: Post[] }[] {
  const groups: { month: string; posts: Post[] }[] = [];
  for (const post of posts) {
    const month = post.date
      ? new Date(`${post.date}T00:00:00`).toLocaleDateString("en-US", {
          month: "long",
          year: "numeric",
        })
      : "Undated";
    const last = groups[groups.length - 1];
    if (last && last.month === month) last.posts.push(post);
    else groups.push({ month, posts: [post] });
  }
  return groups;
}

export function formatShortDate(date: string | null): string {
  if (!date) return "—";
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
}

function shuffle<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Home's feed, as in the iOS app: newest day first, but within a day the
 *  sections come in a fresh random order on every visit — Startup no longer
 *  always leads — and take turns one issue at a time, so a section that
 *  published eight articles does not fill the screen. A section's own issues
 *  keep their order, so part 1 still comes before part 2. */
export function mixedFeed(posts: Record<SectionKey, Post[]>, limit: number): Post[] {
  const byDate = new Map<string, Map<SectionKey, Post[]>>();
  for (const key of ORDER) {
    for (const post of posts[key]) {
      const day = post.date ?? "";
      if (!byDate.has(day)) byDate.set(day, new Map());
      const sections = byDate.get(day)!;
      if (!sections.has(key)) sections.set(key, []);
      sections.get(key)!.push(post);
    }
  }
  const out: Post[] = [];
  for (const day of [...byDate.keys()].sort().reverse()) {
    const sections = byDate.get(day)!;
    const order = shuffle([...sections.keys()]);
    while (out.length < limit && [...sections.values()].some((l) => l.length)) {
      for (const key of order) {
        const next = sections.get(key)!.shift();
        if (next) out.push(next);
      }
    }
    if (out.length >= limit) break;
  }
  return out.slice(0, limit);
}

/** Explore: a random draw from the whole archive, every section and month. */
export function exploreDraw(posts: Record<SectionKey, Post[]>, count: number): Post[] {
  return shuffle(ORDER.flatMap((key) => posts[key])).slice(0, count);
}

export { shuffle };
