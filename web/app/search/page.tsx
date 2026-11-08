import PageTransition from "@/components/PageTransition";
import SearchPanel from "@/components/SearchPanel";
import { exploreDraw } from "@/lib/feed";
import { getMode } from "@/lib/mode-server";
import { getAllPosts } from "@/lib/posts";
import type { SectionKey } from "@/lib/types";

export const metadata = { title: "Explore" };
// A new draw on every visit, like Instagram's Explore. The lists themselves
// come from the shared five-minute cache, so this costs no extra queries.
export const dynamic = "force-dynamic";

export default async function ExplorePage() {
  const [all, mode] = await Promise.all([getAllPosts(), getMode()]);
  // Only the reader's mode, Japan or China.
  const posts = Object.fromEntries(
    Object.entries(all).map(([k, v]) => [k, mode.sections.includes(k as SectionKey) ? v : []])
  ) as typeof all;
  const explore = exploreDraw(posts, 150).map((p) => ({
    id: p.id,
    section: p.section,
    title: p.title,
    date: p.date,
    series: p.series,
    summary: p.summary,
    cover: p.cover ?? null,
  }));
  return (
    <PageTransition>
      <SearchPanel explore={explore} sections={mode.sections} />
    </PageTransition>
  );
}
