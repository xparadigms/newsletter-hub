import { notFound } from "next/navigation";
import StoryViewer from "@/components/story/StoryViewer";
import { getSection } from "@/lib/config";
import { findAdjacent } from "@/lib/feed";
import { getPost, getPosts } from "@/lib/notion";
import { buildDeck } from "@/lib/story";
import { annotateBlocks, readingTime } from "@/lib/text";

export const revalidate = 300;

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
  const description = post.summary ?? `${section.title} in story form.`;
  return {
    title: `${post.title} — Story`,
    description,
    openGraph: {
      type: "article",
      title: post.title,
      description,
      url: `/story/${section.key}/${id}`,
    },
  };
}

export default async function StoryPage({
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
  const deck = buildDeck(annotated, post, section, readingTime(annotated));
  const { prev, next } = findAdjacent(sectionPosts, post.id);

  return (
    <StoryViewer
      cards={deck}
      sectionKey={section.key}
      title={section.label}
      nav={{
        // "next" in a story feed means the next issue chronologically, which is
        // the newer neighbour.
        nextHref: next ? `/story/${next.section}/${next.id}` : null,
        prevHref: prev ? `/story/${prev.section}/${prev.id}` : null,
        closeHref: `/section/${section.key}`,
      }}
    />
  );
}
