import PageTransition from "@/components/PageTransition";
import SectionAvatar from "@/components/home/SectionAvatar";
import PrefetchLink from "@/components/PrefetchLink";
import { SECTIONS } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import { getAllPosts } from "@/lib/posts";
import type { Section } from "@/lib/types";

export const revalidate = 300;
export const metadata = { title: "Sections" };

// Every newsletter, as an iOS inset list. Paused ones sit apart: their
// archives still open, but nothing new arrives.
export default async function SectionsPage() {
  const posts = await getAllPosts();
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
        <ul className="inset-list">{SECTIONS.filter((s) => !s.hideInNav).map(row)}</ul>
        <span className="label inset-list__header">Paused</span>
        <ul className="inset-list">{SECTIONS.filter((s) => s.hideInNav).map(row)}</ul>
      </div>
    </PageTransition>
  );
}
