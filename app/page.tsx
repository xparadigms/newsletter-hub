import Link from "next/link";
import { after } from "next/server";
import LatestRail from "@/components/LatestRail";
import PullToRefresh from "@/components/PullToRefresh";
import SectionModule from "@/components/SectionModule";
import { getSection, SECTIONS, SITE } from "@/lib/config";
import { flattenLatest, formatShortDate, pickLead } from "@/lib/feed";
import { getAllPosts } from "@/lib/notion";
import { warmRecent } from "@/lib/warm";

export const revalidate = 300;
// Warming runs in after(), which shares this invocation's time budget. The
// default 10s cuts a pass off after two issues; 60s lets a full pass finish.
// The page itself still returns in well under a second.
export const maxDuration = 60;

function formatDate(date: string | null): string | null {
  if (!date) return null;
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default async function Home() {
  const posts = await getAllPosts();
  const latest = flattenLatest(posts, 20);
  const lead = pickLead(latest);
  const leadSection = lead ? getSection(lead.section) : null;
  const rest = latest.filter((p) => p.id !== lead?.id);
  const secondary = rest.slice(0, 3);
  const rail = rest.slice(3, 9);
  // The lead, secondary row and rail are the most likely next taps.
  after(() => warmRecent([lead, ...secondary, ...rail].filter((p) => p !== null)));

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="container front">
      <PullToRefresh />
      <div className="front__masthead">
        <span className="label">{today}</span>
        <span className="label front__tagline">{SITE.tagline}</span>
      </div>

      {lead && leadSection && (
        <div className="front__top">
          <article className="lead">
            <span className="label">
              {leadSection.number} / {leadSection.label}
            </span>
            {/* h2: the nav bar's large title is the page's h1. */}
            <h2 className="lead__headline">
              <Link href={`/post/${lead.section}/${lead.id}`} prefetch={false}>
                {lead.title}
              </Link>
            </h2>
            {lead.summary && <p className="lead__deck">{lead.summary}</p>}
            <div className="lead__meta">
              <span className="label">{formatDate(lead.date)}</span>
              <Link
                href={`/post/${lead.section}/${lead.id}`}
                className="arrow-link"
                prefetch={false}
              >
                Read issue <span aria-hidden>→</span>
              </Link>
            </div>

            {secondary.length > 0 && (
              <div className="secondary">
                {secondary.map((post) => {
                  const s = getSection(post.section);
                  return (
                    <Link
                      key={post.id}
                      href={`/post/${post.section}/${post.id}`}
                      className="secondary__item"
                      prefetch={false}
                    >
                      <span className="label">
                        {s?.label} · {formatShortDate(post.date)}
                      </span>
                      <span className="secondary__title">{post.title}</span>
                    </Link>
                  );
                })}
              </div>
            )}
          </article>
          <LatestRail posts={rail} />
        </div>
      )}

      <div className="front__sections">
        {SECTIONS.map((section) => (
          <SectionModule
            key={section.key}
            section={section}
            posts={posts[section.key].slice(0, 6)}
          />
        ))}
      </div>
    </div>
  );
}
