import { notFound } from "next/navigation";
import { after } from "next/server";
import PageTransition from "@/components/PageTransition";
import PostList from "@/components/PostList";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, SECTIONS, SITE } from "@/lib/config";
import { groupByMonth } from "@/lib/feed";
import { getPosts } from "@/lib/notion";
import { warmRecent } from "@/lib/warm";

export const revalidate = 300;
// Warming runs in after(), which shares this invocation's time budget. The
// default 10s cuts a pass off after two issues; 60s lets a full pass finish.
// The page itself still returns in well under a second.
export const maxDuration = 60;

export function generateStaticParams() {
  return SECTIONS.map((s) => ({ key: s.key }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const section = getSection((await params).key);
  if (!section) return { title: "Not found" };
  return {
    title: section.label,
    description: section.description,
    openGraph: {
      title: `${section.title} — ${SITE.name}`,
      description: section.description,
      url: `/section/${section.key}`,
    },
  };
}

export default async function SectionPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const section = getSection((await params).key);
  if (!section) notFound();

  const posts = await getPosts(section.key);
  const groups = groupByMonth(posts);

  // Fill the article cache for this section's newest issues once the list has
  // been sent, so the reader's next tap doesn't wait on Notion.
  after(() => warmRecent(posts));

  return (
    <PageTransition>
      <PullToRefresh />
      {/* The nav bar's large title carries the section name and the page's h1. */}
      <div className="page-head">
        <div className="container">
          <p>{section.description}</p>
        </div>
      </div>
      <section className="section section--flat">
        <div className="container">
          {groups.length === 0 && (
            <p className="section__desc">Nothing published here yet.</p>
          )}
          {groups.map((group) => (
            <div key={group.month}>
              <span className="label month-label">{group.month}</span>
              <PostList posts={group.posts} />
            </div>
          ))}
        </div>
      </section>
    </PageTransition>
  );
}
