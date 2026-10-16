import FeedPost, { type FeedItem } from "@/components/home/FeedPost";
import StoryTray, { type TrayEntry } from "@/components/home/StoryTray";
import PageTransition from "@/components/PageTransition";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { flattenLatest, formatShortDate } from "@/lib/feed";
import { getAllPosts } from "@/lib/posts";

export const revalidate = 300;

function formatDate(date: string | null): string | null {
  if (!date) return null;
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

// Home, laid out like Instagram's: a tray of section stories across the top,
// then one post per issue, newest first — the same shape as the iOS app.
export default async function Home() {
  const posts = await getAllPosts();

  const tray: TrayEntry[] = NAV_SECTIONS.flatMap((s) => {
    const newest = posts[s.key][0];
    return newest ? [{ section: s.key, label: s.label, id: newest.id }] : [];
  });

  const feed: FeedItem[] = flattenLatest(posts, 40).map((p) => {
    const s = getSection(p.section)!;
    return {
      id: p.id,
      section: p.section,
      title: p.title,
      date: p.date,
      series: p.series,
      summary: p.summary,
      sectionTitle: s.title,
      sectionLabel: s.label,
      sectionNumber: s.number,
      longDate: formatDate(p.date),
      shortDate: formatShortDate(p.date),
    };
  });

  return (
    <PageTransition>
      <div className="home">
        <PullToRefresh />
        <StoryTray entries={tray} />
        <div className="feed">
          {feed.length === 0 && <p className="feed__empty">Nothing published yet.</p>}
          {feed.map((item) => (
            <FeedPost key={`${item.section}/${item.id}`} item={item} />
          ))}
        </div>
      </div>
    </PageTransition>
  );
}
