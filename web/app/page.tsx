import FeedPost, { type FeedItem } from "@/components/home/FeedPost";
import StoryTray, { type TrayEntry } from "@/components/home/StoryTray";
import PageTransition from "@/components/PageTransition";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { formatShortDate, mixedFeed, shuffle } from "@/lib/feed";
import { getAllPosts } from "@/lib/posts";

// Rendered per visit, so the order changes every time — the lists come from
// the shared five-minute cache, so this costs no extra queries.
export const dynamic = "force-dynamic";

function formatDate(date: string | null): string | null {
  if (!date) return null;
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

// Home, laid out like Instagram's: a tray of section stories across the top,
// then one post per issue, newest day first with the sections shuffled on
// every visit — the same shape and order as the iOS app.
export default async function Home() {
  const posts = await getAllPosts();

  // Shuffled each visit too; the tray still puts unread sections first.
  const tray: TrayEntry[] = shuffle(NAV_SECTIONS).flatMap((s) => {
    const newest = posts[s.key][0];
    return newest ? [{ section: s.key, label: s.label, id: newest.id }] : [];
  });

  const feed: FeedItem[] = mixedFeed(posts, 40).map((p) => {
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
