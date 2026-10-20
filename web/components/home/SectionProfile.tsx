"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import PostTile, { type TilePost } from "@/components/home/PostTile";
import SectionAvatar from "@/components/home/SectionAvatar";
import { clearStoryQueue } from "@/components/home/stories";
import { SITE } from "@/lib/config";
import { useLibrary } from "@/lib/library";
import type { SectionKey } from "@/lib/types";

/** A section's page as an Instagram profile — the parts that depend on what
 *  this reader has read and saved: the ring, the counts, Play Story. */
export function SectionProfileHead({
  section,
  title,
  description,
  latest,
  newest,
  total,
}: {
  section: SectionKey;
  title: string;
  description: string;
  latest: string | null;
  newest: TilePost | null;
  total: number;
}) {
  const router = useRouter();
  const { read, saved, isRead } = useLibrary();
  const readHere = read.filter((p) => p.section === section).length;
  const savedHere = saved.filter((p) => p.section === section).length;
  const play = () => {
    if (!newest) return;
    clearStoryQueue();
    router.push(`/story/${newest.section}/${newest.id}`, { transitionTypes: ["nav-present"] });
  };
  const share = async () => {
    const url = `${SITE.url}/section/${section}`;
    try {
      if (navigator.share) await navigator.share({ title, url });
      else await navigator.clipboard.writeText(url);
    } catch {}
  };

  return (
    <header className="profile__head">
      <div className="profile__top">
        <button type="button" className="profile__avatar-button" onClick={play} disabled={!newest}
                aria-label="Play the newest issue as a story">
          <SectionAvatar section={section} size={84} unseen={!!newest && !isRead(newest)} />
        </button>
        <dl className="profile__stats">
          <div><dt>posts</dt><dd>{total}</dd></div>
          <div><dt>read</dt><dd>{readHere}</dd></div>
          <div><dt>saved</dt><dd>{savedHere}</dd></div>
        </dl>
      </div>
      <p className="profile__name">{title}</p>
      <p className="profile__bio">{description}</p>
      {latest && <p className="profile__latest">Latest · {latest}</p>}
      <div className="profile__buttons">
        <button type="button" className="profile__button profile__button--primary" onClick={play} disabled={!newest}>
          ▶ Play Story
        </button>
        <button type="button" className="profile__button" onClick={share}>
          Share
        </button>
      </div>
    </header>
  );
}

/** Every issue the section has published, as a grid or as a list by month. */
export function SectionShelf({ posts, list }: { posts: TilePost[]; list: React.ReactNode }) {
  const [view, setView] = useState<"grid" | "list">("grid");
  return (
    <>
      <div className="profile__tabs" role="tablist">
        <button type="button" role="tab" aria-selected={view === "grid"} aria-label="Grid"
                className="profile__tab" onClick={() => setView("grid")}>
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3.5" y="3.5" width="17" height="17" rx="2" /><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17" />
          </svg>
        </button>
        <button type="button" role="tab" aria-selected={view === "list"} aria-label="List"
                className="profile__tab" onClick={() => setView("list")}>
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round">
            <path d="M8.5 6.5h12M8.5 12h12M8.5 17.5h12M4 6.5h.01M4 12h.01M4 17.5h.01" />
          </svg>
        </button>
      </div>
      {posts.length === 0 ? (
        <p className="profile__empty">Nothing published here yet.</p>
      ) : view === "grid" ? (
        <ul className="grid">
          {posts.map((p) => (
            <li key={p.id}>
              <PostTile post={p} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="container section-list">{list}</div>
      )}
    </>
  );
}
