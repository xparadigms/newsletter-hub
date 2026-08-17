import Link from "next/link";
import { notFound } from "next/navigation";
import { renderAnnotated } from "@/components/ArticleBlocks";
import LangToggle from "@/components/LangToggle";
import PageTransition from "@/components/PageTransition";
import TableOfContents from "@/components/TableOfContents";
import { getSection, SECTIONS, SITE } from "@/lib/config";
import { findAdjacent, formatShortDate } from "@/lib/feed";
import { getAllPosts, getPost, getPosts } from "@/lib/notion";
import { annotateBlocks, buildToc, readingTime } from "@/lib/text";

// A published issue is immutable and its body is cached until /api/revalidate
// says otherwise, so re-rendering this HTML often only reproduces the same
// output. In practice Next caps this at the 300s of getPosts, which the page
// awaits for its prev/next links — a route's revalidate is the minimum of the
// segment config and every cache lifetime read during the render. Left at an
// hour because the cap is a side effect of the adjacent-issue lookup rather
// than anything this page wants, and because a regeneration is now cheap: both
// the list and the body come back from cache without touching Notion.
export const revalidate = 3600;

// Each issue costs ~45 Notion calls to assemble, so prerendering the whole
// archive would blow Notion's rate limit and fail the build. Prerender only the
// newest issues — the ones the front page links to. Everything older renders on
// demand once and is then served from the ISR cache (stale-while-revalidate),
// so no reader waits on Notion twice.
const PRERENDER_PER_SECTION = 3;

export async function generateStaticParams() {
  const posts = await getAllPosts();
  return SECTIONS.flatMap((s) =>
    posts[s.key]
      .slice(0, PRERENDER_PER_SECTION)
      .map((p) => ({ section: s.key, id: p.id }))
  );
}

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

export async function generateMetadata({
  params,
}: {
  params: Promise<{ section: string; id: string }>;
}) {
  const { section: sectionKey, id } = await params;
  const section = getSection(sectionKey);
  if (!section) return { title: "Not found" };
  const post = await getPost(id, section.key);
  if (!post) return { title: "Not found" };
  const description =
    post.summary ?? `${section.title} — ${SITE.name} by Heechang.`;
  return {
    title: post.title,
    description,
    openGraph: {
      type: "article",
      title: post.title,
      description,
      publishedTime: post.date ?? undefined,
      url: `/post/${section.key}/${id}`,
    },
    twitter: { title: post.title, description },
  };
}

export default async function PostPage({
  params,
}: {
  params: Promise<{ section: string; id: string }>;
}) {
  const { section: sectionKey, id } = await params;
  const section = getSection(sectionKey);
  if (!section) notFound();

  const [post, sectionPosts] = await Promise.all([
    getPost(id, section.key),
    getPosts(section.key),
  ]);
  if (!post) notFound();

  const annotated = annotateBlocks(post.blocks);
  const hasJa = annotated.some((a) => a.lang === "ja");
  const hasKo = annotated.some((a) => a.lang === "ko");
  const minutes = readingTime(annotated);
  const toc = buildToc(annotated);
  const { prev, next } = findAdjacent(sectionPosts, post.id);
  const date = formatDate(post.date);

  return (
    <PageTransition>
      <article className="article">
        <div className="article__layout">
          <div className="article__col">
            {/* Back lives in the nav bar now. */}
            <div className="article__meta">
              <span className="label">
                {[post.series, date, `${minutes} min read`]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              {(hasJa || hasKo) && <LangToggle />}
            </div>
            <h1>{post.title}</h1>
            {/* data-multi gates the default "hide English" rule so English-only
                issues never render blank. */}
            <div
              className="article__body"
              data-section={section.key}
              data-multi={hasJa || hasKo ? "" : undefined}
            >
              {annotated.length > 0 ? (
                annotated.map(renderAnnotated)
              ) : (
                <p>This entry has no content yet.</p>
              )}
            </div>
            {(prev || next) && (
              <nav className="article__nav" aria-label="Adjacent issues">
                <div>
                  {prev && (
                    <Link
                      href={`/post/${prev.section}/${prev.id}`}
                      className="article__nav-link"
                      transitionTypes={["nav-back"]}
                    >
                      <span className="label">
                        ← Previous · {formatShortDate(prev.date)}
                      </span>
                      <span className="article__nav-title">{prev.title}</span>
                    </Link>
                  )}
                </div>
                <div>
                  {next && (
                    <Link
                      href={`/post/${next.section}/${next.id}`}
                      className="article__nav-link article__nav-link--next"
                      transitionTypes={["nav-forward"]}
                    >
                      <span className="label">
                        Next · {formatShortDate(next.date)} →
                      </span>
                      <span className="article__nav-title">{next.title}</span>
                    </Link>
                  )}
                </div>
              </nav>
            )}
          </div>
          {toc.length > 1 && <TableOfContents items={toc} />}
        </div>
      </article>
    </PageTransition>
  );
}
