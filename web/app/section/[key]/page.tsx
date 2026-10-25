import { notFound } from "next/navigation";
import CompanyRequest from "@/components/CompanyRequest";
import GenerateButton from "@/components/GenerateButton";
import { SectionProfileHead, SectionShelf } from "@/components/home/SectionProfile";
import PageTransition from "@/components/PageTransition";
import PostList from "@/components/PostList";
import PullToRefresh from "@/components/PullToRefresh";
import { getSection, SECTIONS, SITE } from "@/lib/config";
import { groupByMonth } from "@/lib/feed";
import { getPosts } from "@/lib/posts";

export const revalidate = 300;
// Warming runs in after(), which shares this invocation's time budget. The
// default 10s cuts a pass off after two issues; 60s lets a full pass finish.
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
  const tiles = posts.map((p) => ({
    id: p.id,
    section: p.section,
    title: p.title,
    date: p.date,
    series: p.series,
    summary: p.summary,
    cover: p.cover ?? null,
  }));
  const newestDate = posts[0]?.date
    ? new Date(`${posts[0].date}T00:00:00`).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  // Laid out like an Instagram profile, as in the iOS app: avatar and counts,
  // the description as the bio, Play Story and Share, Generate, then every
  // issue as a grid — or as the old list by month.
  return (
    <PageTransition>
      <PullToRefresh />
      <div className="profile">
        <SectionProfileHead
          section={section.key}
          title={section.title}
          description={section.description}
          latest={newestDate}
          newest={tiles[0] ?? null}
          total={posts.length}
        />
        <div className="profile__generate">
          <GenerateButton section={section.key} />
          {section.key === "stocks" && <CompanyRequest />}
        </div>
        <SectionShelf
          posts={tiles}
          list={groups.map((group) => (
            <div key={group.month} className="month-group">
              <span className="label month-label">{group.month}</span>
              <PostList posts={group.posts} />
            </div>
          ))}
        />
      </div>
    </PageTransition>
  );
}
