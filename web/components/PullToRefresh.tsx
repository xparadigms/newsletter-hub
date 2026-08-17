"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

const TRIGGER = 72; // px of pull that commits a refresh
const MAX = 110; // px the indicator can travel
const RESISTANCE = 0.5; // drag feels weighted, like UIRefreshControl

export default function PullToRefresh() {
  const router = useRouter();
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!("ontouchstart" in window)) return;
    const node = el.current;
    if (!node) return;

    let startY = 0;
    let active = false;
    let distance = 0;
    let busy = false;

    // Written straight to the DOM: re-rendering React on every touchmove is
    // what makes a drag feel sticky.
    const paint = (d: number, animate: boolean) => {
      node.style.transition = animate
        ? "transform var(--dur-slow) var(--ease-ios), opacity var(--dur-base) var(--ease-out)"
        : "none";
      node.style.transform = `translate3d(0, ${d}px, 0)`;
      node.style.opacity = String(Math.min(1, d / 40));
      node.dataset.ready = String(d >= TRIGGER);
    };

    const onStart = (e: TouchEvent) => {
      if (busy || e.touches.length !== 1 || window.scrollY > 0) return;
      startY = e.touches[0].clientY;
      active = true;
      distance = 0;
    };

    const onMove = (e: TouchEvent) => {
      if (!active) return;
      const delta = e.touches[0].clientY - startY;
      if (delta <= 0 || window.scrollY > 0) {
        if (distance > 0) paint(0, true);
        distance = 0;
        active = false;
        return;
      }
      distance = Math.min(MAX, delta * RESISTANCE);
      if (distance > 4) e.preventDefault();
      paint(distance, false);
    };

    const onEnd = () => {
      if (!active) return;
      active = false;
      if (distance >= TRIGGER) {
        busy = true;
        node.dataset.busy = "true";
        paint(TRIGGER, true);
        router.refresh();
        window.setTimeout(() => {
          busy = false;
          node.dataset.busy = "false";
          paint(0, true);
        }, 900);
      } else {
        paint(0, true);
      }
      distance = 0;
    };

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, [router]);

  return (
    <div ref={el} className="ptr" data-busy="false" data-ready="false" aria-hidden>
      <span className="ptr__spinner" />
    </div>
  );
}
