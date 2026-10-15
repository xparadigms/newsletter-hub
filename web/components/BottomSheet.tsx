"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const DISMISS_DISTANCE = 96;
const DISMISS_VELOCITY = 0.6;
// The exit slide is --dur-sheet; this only covers transitionend never arriving.
const EXIT_FALLBACK = 650;

export default function BottomSheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const drag = useRef(0);
  const startY = useRef(0);
  const startT = useRef(0);
  // Still mounted for the length of the exit slide after `open` goes false.
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setClosing(false);
      return;
    }
    if (!mounted) return;
    setClosing(true);
    const node = panel.current;
    let timer = 0;
    const done = () => {
      window.clearTimeout(timer);
      node?.removeEventListener("transitionend", onEnd);
      setMounted(false);
      setClosing(false);
    };
    const onEnd = (e: TransitionEvent) => {
      if (e.target === node && e.propertyName === "transform") done();
    };
    node?.addEventListener("transitionend", onEnd);
    timer = window.setTimeout(done, EXIT_FALLBACK);
    return () => {
      window.clearTimeout(timer);
      node?.removeEventListener("transitionend", onEnd);
    };
    // `mounted` is read, not reacted to: only a change of `open` starts this.
  }, [open]);

  // Lock the page behind the sheet without losing the reader's position —
  // position:fixed alone snaps iOS back to the top on release.
  useEffect(() => {
    if (!open) return;
    const y = window.scrollY;
    const { style } = document.body;
    const prev = {
      position: style.position,
      top: style.top,
      width: style.width,
      overflow: style.overflow,
    };
    style.position = "fixed";
    style.top = `-${y}px`;
    style.width = "100%";
    style.overflow = "hidden";
    return () => {
      style.position = prev.position;
      style.top = prev.top;
      style.width = prev.width;
      style.overflow = prev.overflow;
      window.scrollTo(0, y);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    drag.current = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !panel.current) return;
      const focusable = panel.current.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted) return null;

  // Swipe down to dismiss. The drag is written straight to the node's
  // transform — going through React state on every touchmove makes it stick.
  const onTouchStart = (e: React.TouchEvent) => {
    startY.current = e.touches[0].clientY;
    startT.current = e.timeStamp;
    drag.current = 0;
    if (panel.current) panel.current.style.transition = "none";
  };
  // Dragging up past the resting point is allowed, but against a resistance
  // that grows with the pull — the sheet gives a little and goes no further.
  const rubberBand = (dy: number) => -12 * Math.log1p(-dy / 12);
  const onTouchMove = (e: React.TouchEvent) => {
    const dy = e.touches[0].clientY - startY.current;
    // Only drag the sheet when its own content is scrolled to the top.
    const scroller = panel.current?.querySelector(".sheet__body");
    if (!scroller || scroller.scrollTop <= 0) {
      drag.current = Math.max(0, dy);
      const y = dy > 0 ? dy : rubberBand(dy);
      if (panel.current)
        panel.current.style.transform = `translate3d(0, ${y}px, 0)`;
    }
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    const elapsed = Math.max(1, e.timeStamp - startT.current);
    const dy = drag.current;
    if (panel.current) {
      // Released, the sheet springs to wherever it is going from where the
      // finger left it; the inline transform hands over to the CSS state.
      panel.current.style.transition = "";
      panel.current.style.transform = "";
    }
    if (dy > DISMISS_DISTANCE || dy / elapsed > DISMISS_VELOCITY) onClose();
    drag.current = 0;
  };

  // Portalled to <body>. Rendered in place, the search sheet sat inside the
  // nav bar, whose backdrop-filter makes it the containing block for fixed
  // descendants — so the "bottom" sheet opened pinned to the bar at the top of
  // the screen.
  return createPortal(
    <>
      <div
        className="sheet-backdrop"
        data-closing={closing}
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panel}
        className="sheet"
        data-closing={closing}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div
          className="sheet__grip"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <span className="sheet__grabber" />
          <span className="label sheet__title">{title}</span>
        </div>
        <div className="sheet__body">{children}</div>
      </div>
    </>,
    document.body
  );
}
