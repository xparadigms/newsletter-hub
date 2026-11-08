import CoverImage from "@/components/home/CoverImage";
import SectionAvatar from "@/components/home/SectionAvatar";
import { Glyph } from "@/components/SectionGlyph";
import PrefetchLink from "@/components/PrefetchLink";
import FilterBar from "@/components/home/FilterBar";
import PageTransition from "@/components/PageTransition";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { formatShortDate, mixedFeed } from "@/lib/feed";
import { getMode } from "@/lib/mode-server";
import type { SectionKey } from "@/lib/types";
import { getAllPosts } from "@/lib/posts";

// Rendered per visit, so the order changes every time — the lists come from
// the shared five-minute cache, so this costs no extra queries.
export const dynamic = "force-dynamic";

// Home: every issue as a row in the Feed tab's style — section and date,
// headline, summary, the cover beside it — newest day first with the sections
// shuffled on every visit, as in the iOS app, and a row of filters just above
// the tab bar. With story mode on, StoryModeToggle opens these as stories.
export default async function Home({ searchParams }: { searchParams: Promise<{ s?: string }> }) {
  const { s: filter } = await searchParams;
  // Only the newsletters of the reader's mode, Japan or China.
  const mode = await getMode();
  const sections = NAV_SECTIONS.filter((x) => mode.sections.includes(x.key));
  const current = sections.some((x) => x.key === filter) ? (filter as SectionKey) : null;
  const all = await getAllPosts();
  // Only the chosen newsletter, or every one the mode mixes — never Podcast
  // Hub, which has its own tab.
  const shown = (k: string) => (current ? k === current : sections.some((x) => x.key === k));
  const posts = Object.fromEntries(Object.entries(all).map(([k, v]) => [k, shown(k) ? v : []])) as typeof all;

  const feed = mixedFeed(posts, 60);

  return (
    <PageTransition>
      <div className="home">
        <PullToRefresh />
        {feed.length === 0 && <p className="feed__empty">Nothing published yet.</p>}
        <ul className="newsfeed__list">
          {feed.map((p) => {
            const s = getSection(p.section)!;
            return (
              <li key={`${p.section}/${p.id}`}>
                <PrefetchLink href={`/post/${p.section}/${p.id}`} className="news" transitionTypes={["nav-forward"]}>
                  <span className="news__text">
                    <span className="news__meta">
                      <SectionAvatar section={p.section} size={18} />
                      <span>{s.title}</span>
                      <span aria-hidden>·</span>
                      <span>{formatShortDate(p.date)}</span>
                    </span>
                    <span className="news__title">{p.title}</span>
                    {p.summary ? (
                      <span className="news__summary">{p.summary}</span>
                    ) : (
                      p.series && <span className="news__summary">{p.series}</span>
                    )}
                  </span>
                  <span className="news__thumb" data-section={p.section}>
                    <Glyph name={p.section} active={false} size={22} />
                    <CoverImage cover={p.cover} className="news__thumb-img" />
                  </span>
                </PrefetchLink>
              </li>
            );
          })}
        </ul>
        <FilterBar base="/" current={current} options={sections.map((x) => ({ key: x.key, label: x.label }))} />
      </div>
    </PageTransition>
  );
}
