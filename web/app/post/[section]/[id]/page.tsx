import Link from "next/link";
import { notFound } from "next/navigation";
import { renderAnnotated } from "@/components/ArticleBlocks";
import FuriganaToggle from "@/components/FuriganaToggle";
import LangToggle from "@/components/LangToggle";
import PageTransition from "@/components/PageTransition";
import TableOfContents from "@/components/TableOfContents";
import { getSection, SECTIONS, SITE } from "@/lib/config";
import { findAdjacent, formatShortDate } from "@/lib/feed";
import { getAllPosts, getPost, getPosts } from "@/lib/posts";
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
  // notFound() rather than a "Not found" title, so metadata is never built for
  // an issue that does not exist.
  //
  // Note this does NOT make the response a 404. With `revalidate` set, Next
  // renders the not-found body and then stores and serves it as a prerender
  // with status 200 — verified against a cache MISS on a fresh path. Getting a
  // true 404 would mean either dropping ISR on this route, or
  // dynamicParams: false with every issue prerendered, which would 404 each new
  // issue until the next deploy. Neither is worth it: the body is correct and
  // the cost is a soft 404 for search engines. /section/<bad> is unaffected and
  // does return 404.
  if (!section) notFound();
  const post = await getPost(id, section.key);
  if (!post) notFound();
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

  const annotated = annotateBlocks(post.blocks, {
    hanLang: section.sourceLang === "zh" ? "zh" : "ja",
  });
  const hasJa = annotated.some((a) => a.lang === "ja");
  const hasKo = annotated.some((a) => a.lang === "ko");
  const hasZh = annotated.some((a) => a.lang === "zh");
  // Only worth offering where there are readings to hide. Pinyin is ruby
  // too, but it is the point of the Chinese sections rather than an aid.
  const hasRuby = annotated.some((a) => a.ruby?.some((s) => s.reading));
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
              {(hasJa || hasKo || hasZh) && <LangToggle source={section.sourceLang === "zh" ? "中文" : "日本語"} />}
            </div>
            <h1>{post.title}</h1>
            {/* data-multi gates the default "hide English" rule so English-only
                issues never render blank. */}
            <div
              className="article__body"
              data-section={section.key}
              data-source-lang={section.sourceLang ?? "ja"}
              data-multi={hasJa || hasKo || hasZh ? "" : undefined}
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
          {/* Floats at the bottom right so it is reachable mid-read. data-with-toc
              lifts it above the contents button, which owns that corner on
              phones. */}
          {hasRuby && (
            <div
              className="article__fab"
              data-with-toc={toc.length > 1 ? "" : undefined}
            >
              <FuriganaToggle />
            </div>
          )}
        </div>
      </article>
    </PageTransition>
  );
}
