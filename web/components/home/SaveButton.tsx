"use client";

import { toggleSaved, useLibrary, type ShelfPost } from "@/lib/library";

export function BookmarkIcon({ filled, size = 24 }: { filled: boolean; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill={filled ? "currentColor" : "none"}
         stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
      <path d="M6 3.5h12a.5.5 0 0 1 .5.5v16.4a.3.3 0 0 1-.48.24L12 16.2l-6.02 4.44a.3.3 0 0 1-.48-.24V4a.5.5 0 0 1 .5-.5Z" />
    </svg>
  );
}

/** The bookmark on the feed, the article and the story. */
export default function SaveButton({ post, className = "icon-button" }: { post: ShelfPost; className?: string }) {
  const { isSaved } = useLibrary();
  const saved = isSaved(post);
  return (
    <button
      type="button"
      className={className}
      data-on={saved}
      onClick={() => toggleSaved(post)}
      aria-label={saved ? "Remove from Saved" : "Save"}
      aria-pressed={saved}
    >
      <BookmarkIcon filled={saved} />
    </button>
  );
}
