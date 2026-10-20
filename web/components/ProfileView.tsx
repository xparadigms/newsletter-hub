"use client";

import Link from "next/link";
import { useState } from "react";
import PostTile from "@/components/home/PostTile";
import { BookmarkIcon } from "@/components/home/SaveButton";
import SectionAvatar from "@/components/home/SectionAvatar";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { routeId, useLibrary } from "@/lib/library";
import type { SectionKey } from "@/lib/types";

type ShelfName = "saved" | "read" | "timeline";

export interface TimelineEntry {
  section: SectionKey;
  first: string; // long date
  count: number;
  /** For a paused newsletter, its last issue's date. */
  pausedSince: string | null;
}

function CalendarIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor"
         strokeWidth={filled ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" fill={filled ? "currentColor" : "none"} />
      <path d="M3.5 10h17M8 3v4M16 3v4" stroke={filled ? "var(--bg)" : "currentColor"} />
    </svg>
  );
}

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
 *  then a grid of the issues saved or read — both lists live in this browser —
 *  or The Brief's timeline, when each newsletter began. */
export default function ProfileView({ timeline }: { timeline: TimelineEntry[] }) {
  const { saved, read } = useLibrary();
  const [shelf, setShelf] = useState<ShelfName>("saved");
  const posts = shelf === "saved" ? saved : shelf === "read" ? read : [];

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
        {(["saved", "read", "timeline"] as const).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={shelf === name}
            aria-label={name === "saved" ? "Saved" : name === "read" ? "Read" : "Timeline"}
            className="profile__tab"
            onClick={() => setShelf(name)}
          >
            {name === "saved" ? (
              <BookmarkIcon filled={shelf === name} />
            ) : name === "read" ? (
              <ClockIcon filled={shelf === name} />
            ) : (
              <CalendarIcon filled={shelf === name} />
            )}
          </button>
        ))}
      </div>

      {shelf === "timeline" ? (
        <Timeline entries={timeline} />
      ) : posts.length === 0 ? (
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
              <PostTile post={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** When each newsletter began, oldest first: the launch, how many issues
 *  since, and for a paused one, when it stopped. */
function Timeline({ entries }: { entries: TimelineEntry[] }) {
  const total = entries.reduce((n, e) => n + e.count, 0);
  return (
    <ol className="timeline">
      {entries.map((e) => {
        const s = getSection(e.section)!;
        return (
          <li key={e.section} className="timeline__item">
            <Link href={`/section/${e.section}`} className="timeline__link" transitionTypes={["nav-forward"]}>
              <SectionAvatar section={e.section} size={34} />
              <span className="timeline__body">
                <span className="timeline__date">{e.first}</span>
                <span className="timeline__title">{s.title} started</span>
                <span className="timeline__desc">{s.description}</span>
                <span className="timeline__meta">
                  {e.count} issues
                  {e.pausedSince && ` · Paused since ${e.pausedSince}`}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
      <li className="timeline__item timeline__item--today">
        <span className="timeline__now" aria-hidden />
        <span className="timeline__body">
          <span className="timeline__date">Today</span>
          <span className="timeline__title">
            {total} issues across {entries.length} newsletters
          </span>
        </span>
      </li>
    </ol>
  );
}
