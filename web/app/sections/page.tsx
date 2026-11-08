import PageTransition from "@/components/PageTransition";
import SectionAvatar from "@/components/home/SectionAvatar";
import { ModeSegmented } from "@/components/ModeSwitch";
import PrefetchLink from "@/components/PrefetchLink";
import { SECTIONS } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import { getMode } from "@/lib/mode-server";
import { getAllPosts } from "@/lib/posts";
import type { Section } from "@/lib/types";

export const metadata = { title: "Sections" };
// The mode comes from a cookie, so the page renders per request; the lists
// come from the shared five-minute cache.
export const dynamic = "force-dynamic";

// The mode's newsletters, as an iOS inset list, under the Japan / China
// switch. Paused ones sit apart: their archives still open, but nothing new
// arrives.
export default async function SectionsPage() {
  const [posts, mode] = await Promise.all([getAllPosts(), getMode()]);
  const row = (s: Section) => {
    const newest = posts[s.key][0];
    return (
      <li key={s.key}>
        <PrefetchLink href={`/section/${s.key}`} className="section-row" transitionTypes={["nav-forward"]}>
          <SectionAvatar section={s.key} size={44} />
          <span className="section-row__text">
            <span className="section-row__title">{s.title}</span>
            <span className="section-row__desc">{s.description}</span>
            {newest && <span className="label">Latest · {formatShortDate(newest.date)}</span>}
          </span>
          <span className="post-row__arrow" aria-hidden />
        </PrefetchLink>
      </li>
    );
  };
  return (
    <PageTransition>
      <div className="container sections-page">
        <ModeSegmented current={mode.key} />
        <ul className="inset-list">{SECTIONS.filter((s) => mode.sections.includes(s.key)).map(row)}</ul>
        <span className="label inset-list__header">Paused</span>
        <ul className="inset-list">{SECTIONS.filter((s) => s.hideInNav).map(row)}</ul>
      </div>
    </PageTransition>
  );
}
