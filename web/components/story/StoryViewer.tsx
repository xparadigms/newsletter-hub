"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { headingContent, renderAnnotated } from "@/components/ArticleBlocks";
import { blockAudio } from "@/lib/text";
import type { SectionKey } from "@/lib/types";
import FuriganaToggle from "@/components/FuriganaToggle";
import LangToggle from "@/components/LangToggle";
import CoverImage from "@/components/home/CoverImage";
import MarkRead from "@/components/home/MarkRead";
import SaveButton from "@/components/home/SaveButton";
import SectionAvatar from "@/components/home/SectionAvatar";
import { queueNeighbour, storyReturn } from "@/components/home/stories";
import { SITE } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import type { ShelfPost } from "@/lib/library";
import type { StoryCard } from "@/lib/story";

export interface StoryNav {
  prevHref: string | null;
  nextHref: string | null;
  closeHref: string;
}

const SWIPE_X = 48;
const SWIPE_DOWN = 90;

function SpeakerIcon({ playing }: { playing: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {playing ? (
        <rect x="6" y="6" width="12" height="12" rx="1.5" />
      ) : (
        <>
          <path d="M4 9.5h3.5L12 5.5v13L7.5 14.5H4z" />
          <path d="M16 9.2a4 4 0 0 1 0 5.6M18.6 6.6a7.5 7.5 0 0 1 0 10.8" />
        </>
      )}
    </svg>
  );
}

function Card({
  card,
  sectionKey,
  sourceLang,
}: {
  card: StoryCard;
  sectionKey: SectionKey;
  sourceLang: "ja" | "zh";
}) {
  if (card.kind === "cover") {
    return (
      <div className="story-card story-card--cover" data-cover={card.cover?.url ? "" : undefined}>
        <CoverImage cover={card.cover} className="story-card__photo" eager />
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
          {card.cover?.url && <span className="label story-card__credit">Photo: {card.cover.credit}</span>}
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
      {card.heading && <h2 className="story-card__heading">{headingContent(card.heading)}</h2>}
      {card.subtitle && (
        <p className="story-card__subtitle" lang="ko">
          {card.subtitle}
        </p>
      )}
      <div
        className="story-card__body article__body"
        data-section={sectionKey}
        data-source-lang={sourceLang}
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
  sourceLang,
  post,
}: {
  cards: StoryCard[];
  nav: StoryNav;
  /** The section's name, shown beside its avatar. */
  title: string;
  sectionKey: SectionKey;
  sourceLang: "ja" | "zh";
  post: ShelfPost;
}) {
  const here = `/story/${post.section}/${post.id}`;
  const router = useRouter();
  const [index, setIndex] = useState(0);
  // Which way the last move went, so the incoming card arrives from that side.
  const [dir, setDir] = useState<"next" | "prev">("next");
  const count = cards.length;
  // Only offer the toggle where there are readings to hide. Pinyin is ruby too,
  // but it is the point of the Chinese sections rather than a reading aid.
  const current = cards[index];
  const cardAudio =
    current?.kind === "content"
      ? current.blocks
          .map((a) => blockAudio(a.block))
          .filter((u): u is string => !!u)
      : [];
  const hasRuby = cards.some(
    (c) => c.kind === "content" && c.blocks.some((b) => b.ruby?.some((s) => s.reading))
  );
  const start = useRef<{ x: number; y: number } | null>(null);
  const bodyAtTop = useRef(true);
  const scrollAtDown = useRef(0);
  // Set whenever pointerup itself navigates. The click that follows arrives
  // after React has swapped the card, so it can land on a tap zone that was
  // underneath the old body and navigate a second time.
  const handledByPointer = useRef(false);

  // One <audio> for the whole viewer, deliberately outside .story-slide so
  // key={index} cannot remount it. iOS grants playback permission to the
  // *element* that first played inside a user gesture; chaining the queue onto
  // this same element is what lets tracks after the first play at all. A fresh
  // Audio() per track would be blocked from the second one on.
  const audioRef = useRef<HTMLAudioElement>(null);
  const queue = useRef<string[]>([]);
  const cursor = useRef(0);
  const [playing, setPlaying] = useState(false);

  const stopAudio = useCallback(() => {
    queue.current = [];
    cursor.current = 0;
    audioRef.current?.pause();
    setPlaying(false);
  }, []);

  const startTrack = useCallback(
    (url: string) => {
      const el = audioRef.current;
      if (!el) return;
      el.src = url;
      // Nothing may be awaited before this: on iOS the user gesture is consumed
      // at the play() call itself.
      el.play().catch((err: DOMException) => {
        // Assigning src aborts the pending play(). That is us starting the next
        // track, not a failure — treating it as one stopped the card mid-queue.
        if (err?.name !== "AbortError") stopAudio();
      });
    },
    [stopAudio]
  );

  const playCard = useCallback(
    (urls: string[]) => {
      if (!urls.length) return;
      queue.current = urls;
      cursor.current = 0;
      setPlaying(true);
      startTrack(urls[0]);
    },
    [startTrack]
  );

  // Shared by ended and error, so a 404 on one sentence skips to the next
  // rather than stranding the card halfway through. Terminates either way.
  const advanceTrack = useCallback(() => {
    const next = cursor.current + 1;
    if (next >= queue.current.length) {
      stopAudio();
      return;
    }
    cursor.current = next;
    startTrack(queue.current[next]);
  }, [startTrack, stopAudio]);

  // Closing sends the story back down to the page it was opened from — Home,
  // a section, the profile — and never onto an issue's full text.
  const close = useCallback(() => {
    router.push(storyReturn() ?? nav.closeHref, { transitionTypes: ["nav-dismiss"] });
  }, [router, nav.closeHref]);

  // Past either end of the deck: opened from the tray, on to the next or back
  // to the previous section, as Instagram moves between accounts; otherwise
  // the neighbouring issue of this section. Past the newest, close.
  const turn = useCallback(
    (step: 1 | -1) => {
      const queued = queueNeighbour(here, step);
      const target = queued !== undefined ? queued : step > 0 ? nav.nextHref : nav.prevHref;
      if (target) router.replace(target);
      else if (step > 0) close();
    },
    [here, nav.nextHref, nav.prevHref, router, close]
  );

  const goNext = useCallback(() => {
    setDir("next");
    setIndex((i) => {
      if (i < count - 1) return i + 1;
      turn(1);
      return i;
    });
  }, [count, turn]);

  const goPrev = useCallback(() => {
    setDir("prev");
    setIndex((i) => {
      if (i > 0) return i - 1;
      turn(-1);
      return i;
    });
  }, [turn]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        // Space activates whatever control has focus. Without this the focused
        // control fired AND the card advanced — and nothing called
        // preventDefault, so the page scrolled too. instanceof Element matters:
        // the target is document.body when nothing is focused.
        const t = e.target;
        if (t instanceof Element && t.closest("a, button")) return;
        e.preventDefault();
        goNext();
        return;
      }
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, close]);

  // Advancing remounts the card, so the button's own state goes with it — the
  // element that is playing does not.
  useEffect(() => {
    stopAudio();
    return stopAudio;
  }, [index, stopAudio]);

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
      if (bodyAtTop.current) close();
      return;
    }
    if (Math.abs(dx) > SWIPE_X && Math.abs(dx) > Math.abs(dy)) {
      handledByPointer.current = true;
      window.setTimeout(() => {
        handledByPointer.current = false;
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
      // Same guard the swipe path uses: without it, a tap on the card body
      // advanced here and then the trailing click hit a zone and advanced
      // again, skipping a story.
      handledByPointer.current = true;
      window.setTimeout(() => {
        handledByPointer.current = false;
      }, 300);
      if (e.clientX < window.innerWidth * 0.32) goPrev();
      else goNext();
    }
  };

  const zone = (dir: "prev" | "next") => () => {
    if (handledByPointer.current) {
      handledByPointer.current = false;
      return;
    }
    if (dir === "next") goNext();
    else goPrev();
  };

  const share = async () => {
    const url = `${SITE.url}/post/${post.section}/${post.id}`;
    try {
      if (navigator.share) await navigator.share({ title: post.title, url });
      else await navigator.clipboard.writeText(url);
    } catch {}
  };

  return (
    <div
      className="story-root"
      data-section={sectionKey}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
    >
      <MarkRead post={post} />

      {/* The card, as an Instagram story: a rounded dark frame holding the
          segment bars, the header and the content. */}
      <div className="story-frame">
        <div className="story-chrome">
          <div className="story-progress" aria-hidden>
            {cards.map((_, i) => (
              <span key={i} className="story-progress__seg" data-state={i <= index ? "done" : "todo"} />
            ))}
          </div>

          <div className="story-topbar">
            <SectionAvatar section={sectionKey} size={32} />
            <span className="story-who">
              <span className="story-who__line">
                <span className="story-who__name">{title}</span>
                <span className="story-who__date">{formatShortDate(post.date)}</span>
              </span>
              <span className="story-who__title">{post.title}</span>
            </span>
            <button type="button" className="story-topbar__close" onClick={close} aria-label="Close story">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="story-langs">
            <LangToggle source={sourceLang === "zh" ? "中文" : "日本語"} />
          </div>
        </div>

        <div className="story-stage">
          <div className="story-slide" key={index} data-dir={dir}>
            <Card card={cards[index]} sectionKey={sectionKey} sourceLang={sourceLang} />
          </div>

          {/* Inside the stage, not the root: as siblings of the fixed root these
              spanned the whole viewport and covered the top bar, so tapping the
              language toggle advanced the card instead of switching language.
              Scoping them here makes that structurally impossible rather than a
              z-index race. The card body still sits above them at z-index 2. */}
          <button type="button" data-zone className="story-zone story-zone--prev" onClick={zone("prev")} aria-label="Previous card" />
          <button type="button" data-zone className="story-zone story-zone--next" onClick={zone("next")} aria-label="Next card" />
        </div>
      </div>

      {/* Instagram's reply row, holding the reading controls. Literal
          <button>s and links with no data-zone, so the pointerup escape hatch
          bails on them and the swipe layer is neutralised over the bar for
          free. Listen is driven by the card on screen: the queue is rebuilt
          from `index` on every render, so it always reads what is visible. */}
      <div className="story-bar">
        {hasRuby && <FuriganaToggle />}
        {cardAudio.length > 0 && (
          <button
            type="button"
            className="story-audio"
            aria-pressed={playing}
            aria-label={playing ? "Stop reading" : "Read this card aloud"}
            onClick={() => (playing ? stopAudio() : playCard(cardAudio))}
          >
            <SpeakerIcon playing={playing} />
            <span>{playing ? "Stop" : "Listen"}</span>
          </button>
        )}
        <span className="story-bar__spacer" />
        <Link href={`/post/${post.section}/${post.id}`} className="icon-button" aria-label="Open the article">
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" />
          </svg>
        </Link>
        <SaveButton post={post} />
        <button type="button" className="icon-button" onClick={share} aria-label="Share">
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
            <path d="M21 3 3 10.5l7.2 2.6L21 3Zm0 0-7.6 18-3.2-7.9" />
          </svg>
        </button>
      </div>

      <audio ref={audioRef} preload="none" onEnded={advanceTrack} onError={advanceTrack} />
    </div>
  );
}
