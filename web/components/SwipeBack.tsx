"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { getDepth, parentPath, setDepth } from "@/lib/nav";

const EDGE = 24; // px from the left edge that starts the gesture
const COMMIT_RATIO = 0.35; // fraction of the viewport that commits the pop
const COMMIT_VELOCITY = 0.5; // px/ms — a flick commits regardless of distance
// Released, the page finishes on the same spring a tapped back button uses.
const SLIDE_MS = 380;
const SLIDE = `transform ${SLIDE_MS}ms var(--spring), box-shadow ${SLIDE_MS}ms var(--spring)`;
// --underlay-dim is registered with @property in globals.css, which is what
// lets a custom property transition at all.
const DIM = `--underlay-dim ${SLIDE_MS}ms var(--spring)`;
const EDGE_SHADOW = "-6px 0 24px rgb(0 0 0 / 14%)";
// Where the page stops tracking the finger 1:1. Resistance past this point is
// what tells the reader the gesture has nowhere further to go.
const RESIST_AT = 0.5; // fraction of the viewport
// This only exists for the case where transitionend never arrives at all.
const COMMIT_FALLBACK = SLIDE_MS + 200;
// Long enough to outlast the view transition the navigation kicks off. See the
// data-swiping note below.
const SWIPE_FLAG_CLEAR = 700;

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
  }, [pathname]);

  useEffect(() => {
    // Pointer-driven browsers already have a back button and their own gesture.
    if (!("ontouchstart" in window)) return;

    const main = document.getElementById("app-main");
    if (!main) return;

    // Nothing real sits behind the outgoing page — there's no snapshot of the
    // previous route to reveal — so a backdrop stands in, parallaxing at a
    // third of the finger's speed. That offset is the whole depth cue: matching
    // the finger would read as two pages sliding, not one page lifting off
    // another.
    const underlay = document.createElement("div");
    underlay.className = "swipe-underlay";
    underlay.hidden = true;
    document.body.appendChild(underlay);

    let startX = 0;
    let startY = 0;
    let startT = 0;
    let dragging = false;
    let decided = false;
    let dx = 0;

    // PageTransition animates untyped navigations as a back slide, which is
    // what makes the nav bar's back button animate. A swipe is untyped too, but
    // it has already painted its own finger-tracked slide — so it flags itself
    // here and the CSS suppresses the view transition for the duration.
    const setSwiping = (on: boolean) => {
      document.documentElement.toggleAttribute("data-swiping", on);
    };

    // Past RESIST_AT each further pixel of finger travel moves the page less,
    // approaching but never reaching the viewport edge.
    const resist = (offset: number) => {
      const limit = window.innerWidth * RESIST_AT;
      if (offset <= limit) return offset;
      const over = offset - limit;
      return limit + (over * limit) / (over + limit);
    };

    const paint = (offset: number, animate: boolean) => {
      const transition = animate ? SLIDE : "";
      main.style.transition = transition;
      main.style.transform = offset ? `translate3d(${offset}px,0,0)` : "";
      // The edge shadow and the dimming beneath both fade with distance, so the
      // page reads as lifting off the one below it and settling back down.
      const progress = Math.min(1, offset / window.innerWidth);
      main.style.boxShadow = offset ? EDGE_SHADOW : "";
      underlay.style.setProperty("--underlay-dim", String(0.1 * (1 - progress)));
      // Only ever revealed here — hiding is left to clear() and reset(), so a
      // cancelled swipe keeps its backdrop for the whole slide home instead of
      // dropping it on the first frame and exposing the bare body behind.
      if (offset > 0) underlay.hidden = false;
      underlay.style.transition = animate ? `${SLIDE}, ${DIM}` : "";
      underlay.style.transform = `translate3d(${
        (offset - window.innerWidth) / 3
      }px,0,0)`;
    };

    const clear = () => {
      main.style.transition = "";
      main.style.transform = "";
      main.style.boxShadow = "";
      underlay.hidden = true;
      underlay.style.transition = "";
      underlay.style.transform = "";
    };

    const reset = () => {
      dragging = false;
      decided = false;
      dx = 0;
      setSwiping(false);
      paint(0, true);
      window.setTimeout(() => {
        main.style.transition = "";
        main.style.boxShadow = "";
        underlay.hidden = true;
        underlay.style.transition = "";
      }, SLIDE_MS + 20);
    };

    // Hand off to the router the moment the slide actually finishes, rather
    // than at a fixed delay. The old fixed 200ms desynchronised from the 280ms
    // paint whenever the main thread was busy — which is exactly when the
    // gesture felt worst.
    const commit = () => {
      let finished = false;
      const done = () => {
        if (finished) return;
        finished = true;
        main.removeEventListener("transitionend", onEndTransition);
        window.clearTimeout(fallback);
        clear();
        if (getDepth() > 0) router.back();
        else {
          router.push(parentPath(route.current), {
            transitionTypes: ["nav-back"],
          });
        }
        // Released only once the navigation's view transition has had time to
        // run and be suppressed. Clearing it earlier would let the animation
        // restart halfway through.
        window.setTimeout(() => setSwiping(false), SWIPE_FLAG_CLEAR);
      };
      const onEndTransition = (event: TransitionEvent) => {
        if (event.propertyName === "transform") done();
      };
      main.addEventListener("transitionend", onEndTransition);
      const fallback = window.setTimeout(done, COMMIT_FALLBACK);
      paint(window.innerWidth, true);
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
        setSwiping(true);
      }
      if (dx < 0) dx = 0;
      e.preventDefault();
      paint(resist(dx), false);
    };

    const onEnd = (e: TouchEvent) => {
      if (!dragging) return;
      const elapsed = Math.max(1, e.timeStamp - startT);
      const velocity = dx / elapsed;
      // Measured against the raw finger travel, not the resisted paint offset —
      // resistance is a display affordance and shouldn't move the threshold.
      const commits =
        dx > window.innerWidth * COMMIT_RATIO || velocity > COMMIT_VELOCITY;

      if (commits && decided) {
        dragging = false;
        decided = false;
        dx = 0;
        commit();
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
      setSwiping(false);
      clear();
      underlay.remove();
    };
  }, [router]);

  return null;
}
