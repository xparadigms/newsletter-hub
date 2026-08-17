"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { renderAnnotated } from "@/components/ArticleBlocks";
import type { SectionKey } from "@/lib/types";
import LangToggle from "@/components/LangToggle";
import type { StoryCard } from "@/lib/story";

export interface StoryNav {
  prevHref: string | null;
  nextHref: string | null;
  closeHref: string;
}

const SWIPE_X = 48;
const SWIPE_DOWN = 90;

function Card({ card, sectionKey }: { card: StoryCard; sectionKey: SectionKey }) {
  if (card.kind === "cover") {
    return (
      <div className="story-card story-card--cover">
        <span className="label story-card__eyebrow">
          {card.sectionNumber} / {card.sectionLabel}
        </span>
        <h1 className="story-card__title">{card.title}</h1>
        {card.summary && <p className="story-card__deck">{card.summary}</p>}
        <div className="story-card__foot">
          <span className="label">
            {[card.series, card.date, `${card.minutes} min read`]
              .filter(Boolean)
              .join(" · ")}
          </span>
          <span className="label">{card.count} cards · tap to begin</span>
        </div>
      </div>
    );
  }

  if (card.kind === "section") {
    return (
      <div className="story-card story-card--section">
        <span className="label story-card__eyebrow">
          Section {card.index} of {card.total}
        </span>
        <h2 className="story-card__section-title">{card.heading}</h2>
      </div>
    );
  }

  return (
    <div className="story-card story-card--content">
      {card.kicker && <span className="label story-card__eyebrow">{card.kicker}</span>}
      {card.heading && <h2 className="story-card__heading">{card.heading}</h2>}
      {card.subtitle && (
        <p className="story-card__subtitle" lang="ko">
          {card.subtitle}
        </p>
      )}
      <div
        className="story-card__body article__body"
        data-section={sectionKey}
        data-multi=""
      >
        {card.blocks.map(renderAnnotated)}
      </div>
    </div>
  );
}

export default function StoryViewer({
  cards,
  nav,
  title,
  sectionKey,
}: {
  cards: StoryCard[];
  nav: StoryNav;
  title: string;
  sectionKey: SectionKey;
}) {
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const count = cards.length;
  const start = useRef<{ x: number; y: number } | null>(null);
  const bodyAtTop = useRef(true);
  const scrollAtDown = useRef(0);
  const swiped = useRef(false);

  const goNext = useCallback(() => {
    setIndex((i) => {
      if (i < count - 1) return i + 1;
      // Past the last card, roll on to the next issue like a story feed.
      router.push(nav.nextHref ?? nav.closeHref);
      return i;
    });
  }, [count, router, nav.nextHref, nav.closeHref]);

  const goPrev = useCallback(() => {
    setIndex((i) => {
      if (i > 0) return i - 1;
      if (nav.prevHref) router.push(nav.prevHref);
      return i;
    });
  }, [router, nav.prevHref]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " ") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "Escape") router.push(nav.closeHref);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, router, nav.closeHref]);

  // Deliberately no prefetch of the neighbouring issues: assembling one costs
  // ~45 Notion calls, so prefetching both on every open triples the load.

  const onPointerDown = (e: React.PointerEvent) => {
    start.current = { x: e.clientX, y: e.clientY };
    // Dragging down is also how you scroll a card's body back up, so dismissing
    // is only allowed when there is nothing above to scroll to. Read it now:
    // by pointerup the scroll position has already changed.
    const body = document.querySelector(".story-card__body");
    bodyAtTop.current = !body || body.scrollTop <= 0;
    scrollAtDown.current = body?.scrollTop ?? 0;
  };

  const onPointerUp = (e: React.PointerEvent) => {
    const from = start.current;
    start.current = null;
    if (!from) return;
    if ((e.target as HTMLElement).closest("a, button:not([data-zone])")) return;
    const dx = e.clientX - from.x;
    const dy = e.clientY - from.y;
    if (dy > SWIPE_DOWN && Math.abs(dy) > Math.abs(dx)) {
      // Swipe down dismisses, as in Instagram — but never mid-scroll.
      if (bodyAtTop.current) router.push(nav.closeHref);
      return;
    }
    if (Math.abs(dx) > SWIPE_X && Math.abs(dx) > Math.abs(dy)) {
      swiped.current = true;
      window.setTimeout(() => {
        swiped.current = false;
      }, 300);
      if (dx < 0) goNext();
      else goPrev();
      return;
    }

    // The card body now sits above the tap zones so it can scroll, which would
    // otherwise cost tap-to-advance over the text. Treat a still tap on the
    // body as a zone tap — unless the gesture actually scrolled it.
    const target = e.target as HTMLElement;
    if (target.closest("[data-zone]")) return; // the zone's own click handles it
    const body = document.querySelector(".story-card__body");
    const scrolled = (body?.scrollTop ?? 0) !== scrollAtDown.current;
    if (!scrolled && Math.abs(dx) < 8 && Math.abs(dy) < 8) {
      if (e.clientX < window.innerWidth * 0.32) goPrev();
      else goNext();
    }
  };

  const zone = (dir: "prev" | "next") => () => {
    if (swiped.current) {
      swiped.current = false;
      return;
    }
    if (dir === "next") goNext();
    else goPrev();
  };

  return (
    <div
      className="story-root"
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
    >
      <div className="story-progress" aria-hidden>
        {cards.map((_, i) => (
          <span key={i} className="story-progress__seg" data-state={i < index ? "done" : i === index ? "active" : "todo"} />
        ))}
      </div>

      <div className="story-topbar">
        <span className="story-topbar__title">{title}</span>
        <LangToggle />
        <button
          type="button"
          className="story-topbar__close"
          onClick={() => router.push(nav.closeHref)}
          aria-label="Close story"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="story-stage">
        <div className="story-slide" key={index}>
          <Card card={cards[index]} sectionKey={sectionKey} />
        </div>
      </div>

      {/* Tap zones sit behind the card content so links stay clickable. */}
      <button type="button" data-zone className="story-zone story-zone--prev" onClick={zone("prev")} aria-label="Previous card" />
      <button type="button" data-zone className="story-zone story-zone--next" onClick={zone("next")} aria-label="Next card" />

      <div className="story-counter label">
        {index + 1} / {count}
      </div>
    </div>
  );
}
