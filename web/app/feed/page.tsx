import FilterBar from "@/components/home/FilterBar";
import PageTransition from "@/components/PageTransition";
import PullToRefresh from "@/components/PullToRefresh";
import SectionAvatar from "@/components/home/SectionAvatar";
import { getSection } from "@/lib/config";
import { getFeed } from "@/lib/posts";
import { getMode } from "@/lib/mode-server";
import type { SectionKey } from "@/lib/types";

export const metadata = { title: "Feed" };
// Times are shown as "2h ago", so the page renders per visit; the data comes
// from a two-minute cache.
export const dynamic = "force-dynamic";

function ago(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins || 1}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

// The latest from every newsletter's sources, collected each hour — the news
// itself, before it becomes an issue. Each item opens on its publisher's site.
export default async function FeedPage({ searchParams }: { searchParams: Promise<{ s?: string }> }) {
  const { s } = await searchParams;
  // The mode's newsletters that have a news feed; Mandarin Basics is a lesson.
  const mode = await getMode();
  const feedSections = mode.feedSections;
  const current = feedSections.includes(s as SectionKey) ? (s as SectionKey) : null;
  const items = await getFeed(current ? [current] : feedSections);

  return (
    <PageTransition>
      <div className="newsfeed">
        <PullToRefresh />
        {/* China mode has one feed, so nothing to choose between. */}
        {feedSections.length > 1 && (
          <FilterBar
            base="/feed"
            current={current}
            options={feedSections.map((key) => ({ key, label: getSection(key)?.label ?? key }))}
          />
        )}

        {items.length === 0 ? (
          <p className="newsfeed__empty">Nothing collected yet — the feed fills every hour.</p>
        ) : (
          <ul className="newsfeed__list">
            {items.map((item) => (
              <li key={item.id}>
                <a href={item.url} target="_blank" rel="noopener noreferrer" className="news">
                  <span className="news__text">
                    <span className="news__meta">
                      <SectionAvatar section={item.section} size={18} />
                      <span>{item.source}</span>
                      <span aria-hidden>·</span>
                      <time dateTime={item.published_at ?? undefined}>{ago(item.published_at)}</time>
                    </span>
                    <span className="news__title">{item.title}</span>
                    {item.summary && <span className="news__summary">{item.summary}</span>}
                  </span>
                  {item.image_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img className="news__image" src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                  )}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PageTransition>
  );
}
