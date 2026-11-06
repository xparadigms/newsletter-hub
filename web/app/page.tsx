import CoverImage from "@/components/home/CoverImage";
import SectionAvatar from "@/components/home/SectionAvatar";
import { Glyph } from "@/components/SectionGlyph";
import PrefetchLink from "@/components/PrefetchLink";
import StoryTray, { type TrayEntry } from "@/components/home/StoryTray";
import PageTransition from "@/components/PageTransition";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { formatShortDate, mixedFeed, shuffle } from "@/lib/feed";
import { getAllPosts } from "@/lib/posts";

// Rendered per visit, so the order changes every time — the lists come from
// the shared five-minute cache, so this costs no extra queries.
export const dynamic = "force-dynamic";

// Home: a tray of section stories across the top, then every issue as a row in
// the Feed tab's style — section and date, headline, summary, the cover beside
// it — newest day first with the sections shuffled on every visit, as in the
// iOS app. With story mode on, StoryModeToggle opens these as stories.
export default async function Home() {
  const posts = await getAllPosts();

  // Shuffled each visit too; the tray still puts unread sections first.
  const tray: TrayEntry[] = shuffle(NAV_SECTIONS).flatMap((s) => {
    const newest = posts[s.key][0];
    return newest ? [{ section: s.key, label: s.label, id: newest.id }] : [];
  });

  const feed = mixedFeed(posts, 60);

  return (
    <PageTransition>
      <div className="home">
        <PullToRefresh />
        <StoryTray entries={tray} />
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
      </div>
    </PageTransition>
  );
}
