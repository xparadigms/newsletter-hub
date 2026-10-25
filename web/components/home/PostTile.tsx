"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import CoverImage from "@/components/home/CoverImage";
import { clearStoryQueue, storyModeOn } from "@/components/home/stories";
import { Glyph } from "@/components/SectionGlyph";
import { getSection } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import { useLibrary, type ShelfPost } from "@/lib/library";

export interface TilePost extends ShelfPost {
  summary?: string | null;
}

/** One square of a grid — a profile's, a section's or Explore's: the issue's
 *  headline on its section's dark card. A tall tile has room for the summary. */
export default function PostTile({
  post,
  tall = false,
  showSection = false,
  unreadDot = false,
}: {
  post: TilePost;
  tall?: boolean;
  showSection?: boolean;
  unreadDot?: boolean;
}) {
  const router = useRouter();
  const { isRead } = useLibrary();
  const href = `/post/${post.section}/${post.id}`;
  const label = getSection(post.section)?.label;
  return (
    <Link
      href={href}
      className="grid__tile"
      data-section={post.section}
      data-tall={tall || undefined}
      data-cover={post.cover?.url ? "" : undefined}
      transitionTypes={["nav-forward"]}
      onClick={(e) => {
        if (!storyModeOn()) return;
        e.preventDefault();
        clearStoryQueue();
        router.push(`/story/${post.section}/${post.id}`, { transitionTypes: ["nav-present"] });
      }}
    >
      <CoverImage cover={post.cover} className="grid__photo" />
      <Glyph name={post.section} active={false} size={14} />
      {unreadDot && !isRead(post) && <i className="grid__dot" aria-label="Unread" />}
      <span className="grid__title">{post.title}</span>
      {tall && post.summary && <span className="grid__summary">{post.summary}</span>}
      <span className="grid__date">
        {showSection ? `${label} · ` : ""}
        {formatShortDate(post.date)}
      </span>
    </Link>
  );
}
