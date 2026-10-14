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
// Entering and leaving pages get different classes, not one per direction.
// UINavigationController's push slides the new page over the old one, and its
// pop slides the old page off the top of the new one — so which snapshot sits
// on top depends on the role as well as the direction, and the CSS can only
// tell the two apart by class.
//
// Tab taps carry "nav-tab": switching tabs on iOS is a swap in place, not a
// push, so those only cross-fade. Opening and closing a story carry
// "nav-present" and "nav-dismiss", and there the page sits still: the screen
// moves as one snapshot (globals.css), which a named page would be lifted out
// of.
//
// The swipe gesture is the exception, and it opts out for itself: SwipeBack
// paints its own finger-tracked slide and sets data-swiping to suppress this
// one, so the two never animate at once.
export const PAGE_ENTER: ViewTransitionClassPerType = {
  "nav-forward": "push-in",
  "nav-back": "pop-in",
  "nav-tab": "tab-in",
  "nav-present": "none",
  "nav-dismiss": "none",
  default: "pop-in",
};

export const PAGE_EXIT: ViewTransitionClassPerType = {
  "nav-forward": "push-out",
  "nav-back": "pop-out",
  "nav-tab": "tab-out",
  "nav-present": "none",
  "nav-dismiss": "none",
  default: "pop-out",
};

// This has to sit inside each page rather than in the layout: layouts persist
// across navigation, so their enter/exit never fire.
//
// The .page wrapper is what gets named, so every page is snapshotted by the
// same box — globals.css stretches it to the screen for the length of a
// transition, which keeps a short page from leaving the one under it showing.
export default function PageTransition({ children }: { children: ReactNode }) {
  return (
    <ViewTransition enter={PAGE_ENTER} exit={PAGE_EXIT} default="none">
      <div className="page">{children}</div>
    </ViewTransition>
  );
}
