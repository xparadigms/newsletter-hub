"use client";

import type { ReactNode } from "react";
import { ViewTransition } from "react";
import type { ViewTransitionClassPerType } from "react";

// Directional page slide, replacing the old template.tsx + <html data-nav> +
// .page-transition keyframes.
//
// Forward taps carry transitionTypes={["nav-forward"]}. Everything untyped
// falls back to the back slide, and that default is doing real work: Next only
// applies transition types on push/replace, so router.back() — the nav bar's
// back button, the browser's, the keyboard's — is structurally untypeable. A
// default of "none" would leave every one of those with no animation at all.
// Treating "untyped" as "history traversal" is right in nearly every case here;
// the one it gets wrong is browser-forward, which this app gives no affordance
// for.
//
// The swipe gesture is the exception, and it opts out for itself: SwipeBack
// paints its own finger-tracked slide and sets data-swiping to suppress this
// one, so the two never animate at once.
const DIRECTIONAL: ViewTransitionClassPerType = {
  "nav-forward": "nav-forward",
  "nav-back": "nav-back",
  default: "nav-back",
};

// This has to sit inside each page rather than in the layout: layouts persist
// across navigation, so their enter/exit never fire.
export default function PageTransition({ children }: { children: ReactNode }) {
  return (
    <ViewTransition enter={DIRECTIONAL} exit={DIRECTIONAL} default="none">
      {children}
    </ViewTransition>
  );
}
