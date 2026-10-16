"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BookmarkIcon } from "@/components/home/SaveButton";
import { clearStoryQueue, storyModeOn } from "@/components/home/stories";
import { Glyph } from "@/components/SectionGlyph";
import { NAV_SECTIONS } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import { routeId, useLibrary, type ShelfPost } from "@/lib/library";

type ShelfName = "saved" | "read";

function ClockIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill={filled ? "currentColor" : "none"}
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" stroke={filled ? "var(--bg)" : "currentColor"} />
    </svg>
  );
}

/** The reader's page, laid out like an Instagram profile: who, a row of counts,
 *  then a grid of the issues saved — or read. Both lists live in this browser. */
export default function ProfileView() {
  const { saved, read } = useLibrary();
  const [shelf, setShelf] = useState<ShelfName>("saved");
  const posts = shelf === "saved" ? saved : read;

  return (
    <div className="profile">
      <header className="profile__head">
        <div className="profile__top">
          <span className="profile__avatar" aria-hidden>
            <span className="profile__avatar-face">
              <span>TB</span>
              <i />
            </span>
          </span>
          <dl className="profile__stats">
            <div><dt>saved</dt><dd>{saved.length}</dd></div>
            <div><dt>read</dt><dd>{read.length}</dd></div>
            <div><dt>sections</dt><dd>{NAV_SECTIONS.length}</dd></div>
          </dl>
        </div>
        <p className="profile__name">Heechang</p>
        <p className="profile__bio">The Brief · daily newsletters on startups, finance, Japan and China</p>
      </header>

      <div className="profile__tabs" role="tablist">
        {(["saved", "read"] as const).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={shelf === name}
            aria-label={name === "saved" ? "Saved" : "Read"}
            className="profile__tab"
            onClick={() => setShelf(name)}
          >
            {name === "saved" ? <BookmarkIcon filled={shelf === name} /> : <ClockIcon filled={shelf === name} />}
          </button>
        ))}
      </div>

      {posts.length === 0 ? (
        <div className="profile__empty">
          <p className="profile__empty-title">{shelf === "saved" ? "Nothing saved yet" : "Nothing read yet"}</p>
          <p>
            {shelf === "saved"
              ? "Tap the bookmark on an issue, or double-tap it in Home, to keep it here."
              : "Issues you open as an article or a story collect here."}
          </p>
        </div>
      ) : (
        <ul className="grid">
          {posts.map((p) => (
            <li key={routeId(p)}>
              <Tile post={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Tile({ post }: { post: ShelfPost }) {
  const router = useRouter();
  const href = `/post/${post.section}/${post.id}`;
  return (
    <Link
      href={href}
      className="grid__tile"
      data-section={post.section}
      transitionTypes={["nav-forward"]}
      onClick={(e) => {
        if (!storyModeOn()) return;
        e.preventDefault();
        clearStoryQueue();
        router.push(`/story/${post.section}/${post.id}`, { transitionTypes: ["nav-present"] });
      }}
    >
      <Glyph name={post.section} active={false} size={14} />
      <span className="grid__title">{post.title}</span>
      <span className="grid__date">{formatShortDate(post.date)}</span>
    </Link>
  );
}
