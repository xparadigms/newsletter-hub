"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import BottomSheet from "@/components/BottomSheet";
import type { TocItem } from "@/lib/text";

// Distance below the sticky header at which a heading counts as "current".
const ACTIVE_OFFSET = 120;

export default function TableOfContents({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string | null>(items[0]?.id ?? null);
  const [open, setOpen] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);

  // Highlight the last heading scrolled past. A rAF-throttled scroll read is
  // simpler and steadier here than IntersectionObserver, whose rootMargin
  // thresholds misfire on the very long sections in these issues.
  useEffect(() => {
    const headings = items
      .map((i) => document.getElementById(i.id))
      .filter((el): el is HTMLElement => el !== null);
    if (headings.length === 0) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      let current = headings[0].id;
      for (const el of headings) {
        if (el.getBoundingClientRect().top <= ACTIVE_OFFSET) current = el.id;
        else break;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [items]);

  // Keep the current section visible inside the rail. These issues run to more
  // headings than fit a viewport, so the rail scrolls internally — and without
  // this it stays wherever it was left, showing a part of the issue you are no
  // longer reading while the entry you want sits clipped above or below.
  //
  // scrollTop rather than scrollIntoView: even with block:"nearest" that call
  // walks every scrollable ancestor, and the nearest one here is the page. It
  // would drag the article out from under the reader to tidy a sidebar.
  useEffect(() => {
    const rail = railRef.current;
    if (!rail || !active) return;
    const link = rail.querySelector<HTMLElement>(`a[href="#${CSS.escape(active)}"]`);
    if (!link) return;

    const pad = 24;
    const top = link.offsetTop - rail.offsetTop;
    const above = top - pad < rail.scrollTop;
    const below = top + link.offsetHeight + pad > rail.scrollTop + rail.clientHeight;
    if (above || below) {
      rail.scrollTo({
        top: Math.max(0, top - rail.clientHeight / 3),
        behavior: "smooth",
      });
    }
  }, [active]);

  const go = useCallback((e: React.MouseEvent, id: string) => {
    e.preventDefault();
    setOpen(false);
    // The sheet restores page scroll as it unmounts, so jump on the next frame
    // to avoid being overwritten by that restore.
    requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#${id}`);
    });
  }, []);

  const list = (
    <ol className="toc__list">
      {items.map((item) => (
        <li key={item.id}>
          <a
            href={`#${item.id}`}
            className={`toc__link${item.level >= 3 ? " toc__link--sub" : ""}`}
            data-active={active === item.id}
            onClick={(e) => go(e, item.id)}
          >
            <span className="toc__text">{item.text}</span>
          </a>
        </li>
      ))}
    </ol>
  );

  return (
    <>
      <nav className="toc" aria-label="Table of contents">
        <div className="toc__inner" ref={railRef}>
          <span className="label toc__heading">Contents</span>
          {list}
        </div>
      </nav>

      <BottomSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Contents"
      >
        {list}
      </BottomSheet>
      <button
        type="button"
        className="toc-fab"
        aria-expanded={open}
        aria-label={open ? "Close table of contents" : "Table of contents"}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        ) : (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
        )}
      </button>
    </>
  );
}
