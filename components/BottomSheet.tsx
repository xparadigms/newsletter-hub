"use client";

import { useEffect, useRef } from "react";

const DISMISS_DISTANCE = 96;
const DISMISS_VELOCITY = 0.6;

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

  if (!open) return null;

  // Swipe down to dismiss. The drag is written straight to the node's
  // transform — going through React state on every touchmove makes it stick.
  const onTouchStart = (e: React.TouchEvent) => {
    startY.current = e.touches[0].clientY;
    startT.current = e.timeStamp;
    drag.current = 0;
    if (panel.current) panel.current.style.transition = "none";
  };
  const onTouchMove = (e: React.TouchEvent) => {
    const dy = e.touches[0].clientY - startY.current;
    // Only drag the sheet when its own content is scrolled to the top.
    const scroller = panel.current?.querySelector(".sheet__body");
    if (dy > 0 && (!scroller || scroller.scrollTop <= 0)) {
      drag.current = dy;
      if (panel.current)
        panel.current.style.transform = `translate3d(0, ${dy}px, 0)`;
    }
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    const elapsed = Math.max(1, e.timeStamp - startT.current);
    const dy = drag.current;
    if (panel.current) panel.current.style.transition = "";
    if (dy > DISMISS_DISTANCE || dy / elapsed > DISMISS_VELOCITY) onClose();
    else if (panel.current) panel.current.style.transform = "";
    drag.current = 0;
  };

  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        className="sheet"
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
    </>
  );
}
