import CoverImage from "@/components/home/CoverImage";
import FilterBar from "@/components/home/FilterBar";
import SectionAvatar from "@/components/home/SectionAvatar";
import { Glyph } from "@/components/SectionGlyph";
import PageTransition from "@/components/PageTransition";
import PrefetchLink from "@/components/PrefetchLink";
import PullToRefresh from "@/components/PullToRefresh";
import { formatShortDate } from "@/lib/feed";
import { getPosts } from "@/lib/posts";

export const metadata = { title: "Podcasts" };
// ?s= picks a show, so the page renders per request; the list itself comes
// from the shared five-minute cache.
export const dynamic = "force-dynamic";

/** A show's filter key: its name, as a URL would spell it. */
function showKey(series: string): string {
  return series.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// Podcast Hub: one article per new episode of the shows in
// podcasts-newsletter/main.py, newest first, with a show filter above the tab
// bar the way Home and Feed have theirs.
export default async function PodcastsPage({ searchParams }: { searchParams: Promise<{ s?: string }> }) {
  const { s } = await searchParams;
  const episodes = await getPosts("podcasts");

  // Shows in the order their latest episodes came out.
  const shows: { key: string; label: string }[] = [];
  for (const e of episodes) {
    if (e.series && !shows.some((x) => x.label === e.series)) shows.push({ key: showKey(e.series), label: e.series });
  }
  const current = shows.some((x) => x.key === s) ? s! : null;
  const shown = current ? episodes.filter((e) => e.series && showKey(e.series) === current) : episodes.slice(0, 80);

  return (
    <PageTransition>
      <div className="home podcasts">
        <PullToRefresh />
        {shown.length === 0 && (
          <p className="feed__empty">The first episodes arrive within six hours — every new one becomes an article here.</p>
        )}
        <ul className="newsfeed__list">
          {shown.map((p) => (
            <li key={p.id}>
              <PrefetchLink href={`/post/podcasts/${p.id}`} className="news" transitionTypes={["nav-forward"]}>
                <span className="news__text">
                  <span className="news__meta">
                    <SectionAvatar section="podcasts" size={18} />
                    <span>{p.series ?? "Podcast"}</span>
                    <span aria-hidden>·</span>
                    <span>{formatShortDate(p.date)}</span>
                  </span>
                  <span className="news__title">{p.title}</span>
                  {p.summary && <span className="news__summary">{p.summary}</span>}
                </span>
                <span className="news__thumb" data-section="podcasts">
                  <Glyph name="podcasts" active={false} size={22} />
                  <CoverImage cover={p.cover} className="news__thumb-img" />
                </span>
              </PrefetchLink>
            </li>
          ))}
        </ul>
        {shows.length > 0 && <FilterBar base="/podcasts" current={current} options={shows} />}
      </div>
    </PageTransition>
  );
}
