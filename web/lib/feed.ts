import type { Post, SectionKey } from "./types";

// Fixed tie-break order for same-day posts in the merged feed (dates are
// date-only, so daily newsletters collide constantly).
const ORDER: SectionKey[] = ["fintech", "startup", "japan", "watch"];

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
