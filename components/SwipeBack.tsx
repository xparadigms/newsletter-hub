"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { getDepth, markDirection, parentPath, setDepth } from "@/lib/nav";

const EDGE = 24; // px from the left edge that starts the gesture
const COMMIT_RATIO = 0.35; // fraction of the viewport that commits the pop
const COMMIT_VELOCITY = 0.5; // px/ms — a flick commits regardless of distance

export default function SwipeBack() {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  // Keep the latest route in a ref so the listeners can stay mounted once.
  const route = useRef(pathname);
  route.current = pathname;

  // Track how deep into the session we are, so "back" knows whether there is
  // anything to pop. A cold entry from a shared link has depth 0.
  useEffect(() => {
    const depth = getDepth();
    if (sessionStorage.getItem("nav-seen") === null) {
      sessionStorage.setItem("nav-seen", "1");
      setDepth(0);
    } else {
      setDepth(depth + 1);
    }
    markDirection("push");
  }, [pathname]);

  useEffect(() => {
    // Pointer-driven browsers already have a back button and their own gesture.
    if (!("ontouchstart" in window)) return;

    const main = document.getElementById("app-main");
    if (!main) return;

    let startX = 0;
    let startY = 0;
    let startT = 0;
    let dragging = false;
    let decided = false;
    let dx = 0;

    const paint = (offset: number, animate: boolean) => {
      main.style.transition = animate ? "transform .28s cubic-bezier(.32,.72,0,1)" : "";
      main.style.transform = offset ? `translate3d(${offset}px,0,0)` : "";
    };

    const reset = () => {
      dragging = false;
      decided = false;
      dx = 0;
      paint(0, true);
      window.setTimeout(() => {
        main.style.transition = "";
      }, 300);
    };

    const onStart = (e: TouchEvent) => {
      if (e.touches.length !== 1) return;
      const t = e.touches[0];
      if (t.clientX > EDGE) return;
      if (route.current === "/") return; // nothing above the front page
      startX = t.clientX;
      startY = t.clientY;
      startT = e.timeStamp;
      dragging = true;
      decided = false;
    };

    const onMove = (e: TouchEvent) => {
      if (!dragging) return;
      const t = e.touches[0];
      dx = t.clientX - startX;
      const dy = t.clientY - startY;

      if (!decided) {
        // Let a mostly-vertical drag scroll the page instead.
        if (Math.abs(dy) > Math.abs(dx)) {
          dragging = false;
          return;
        }
        if (Math.abs(dx) < 8) return;
        decided = true;
      }
      if (dx < 0) dx = 0;
      e.preventDefault();
      paint(dx, false);
    };

    const onEnd = (e: TouchEvent) => {
      if (!dragging) return;
      const elapsed = Math.max(1, e.timeStamp - startT);
      const velocity = dx / elapsed;
      const commit =
        dx > window.innerWidth * COMMIT_RATIO || velocity > COMMIT_VELOCITY;

      if (commit && decided) {
        markDirection("pop");
        paint(window.innerWidth, true);
        window.setTimeout(() => {
          main.style.transition = "";
          main.style.transform = "";
          if (getDepth() > 0) router.back();
          else router.push(parentPath(route.current));
        }, 200);
        dragging = false;
        decided = false;
        dx = 0;
        return;
      }
      reset();
    };

    // Non-passive: the horizontal drag needs preventDefault to stop scrolling.
    main.addEventListener("touchstart", onStart, { passive: true });
    main.addEventListener("touchmove", onMove, { passive: false });
    main.addEventListener("touchend", onEnd, { passive: true });
    main.addEventListener("touchcancel", reset, { passive: true });
    return () => {
      main.removeEventListener("touchstart", onStart);
      main.removeEventListener("touchmove", onMove);
      main.removeEventListener("touchend", onEnd);
      main.removeEventListener("touchcancel", reset);
      main.style.transform = "";
      main.style.transition = "";
    };
  }, [router]);

  return null;
}
