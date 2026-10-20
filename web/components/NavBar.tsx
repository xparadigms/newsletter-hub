"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, ViewTransition } from "react";
import { PAGE_ENTER, PAGE_EXIT } from "@/components/PageTransition";
import StoryModeToggle from "@/components/StoryModeToggle";
import ThemeToggle from "@/components/ThemeToggle";
import { getSection, SITE } from "@/lib/config";
import { getDepth, parentPath } from "@/lib/nav";

// Scroll distance after which the large title has fully collapsed into the bar.
const COLLAPSE_AT = 44;
// How long a back tap holds the old screen while the previous route renders.
// Popping is served from the router cache, so this is only ever a backstop.
const POP_WAIT = 800;

function titleFor(pathname: string): { title: string; back: string | null } {
  if (pathname.startsWith("/post/")) {
    const key = pathname.split("/")[2] ?? "";
    return { title: getSection(key)?.label ?? SITE.name, back: getSection(key)?.label ?? "Back" };
  }
  if (pathname.startsWith("/section/")) {
    const key = pathname.split("/")[2] ?? "";
    return { title: getSection(key)?.title ?? SITE.name, back: null };
  }
  if (pathname === "/sections") return { title: "Sections", back: null };
  if (pathname === "/search") return { title: "Explore", back: null };
  if (pathname === "/profile") return { title: "Profile", back: null };
  if (pathname === "/offline") return { title: "Offline", back: "Back" };
  return { title: SITE.name, back: null };
}

export default function NavBar() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [articleTitle, setArticleTitle] = useState("");
  // Resolves the pending pop transition once the previous route is on screen.
  const popped = useRef<(() => void) | null>(null);

  // Layout effect: the route has committed to the DOM but not yet painted,
  // which is exactly when the transition should capture it.
  useLayoutEffect(() => {
    popped.current?.();
    popped.current = null;
  }, [pathname]);

  const { title, back } = titleFor(pathname);
  // Articles have their own headline, so the bar stays compact and instead
  // reveals that headline once it scrolls out of view — the iOS pattern.
  const isArticle = pathname.startsWith("/post/");

  useEffect(() => {
    const heading = isArticle
      ? document.querySelector<HTMLElement>(".article h1")
      : null;
    setArticleTitle(heading?.textContent?.trim() ?? "");

    let frame = 0;
    const update = () => {
      frame = 0;
      const threshold = heading
        ? heading.offsetTop + heading.offsetHeight - 56
        : COLLAPSE_AT;
      setCollapsed(window.scrollY > threshold);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [pathname, isArticle]);

  const goBack = () => {
    // A cold entry (shared link, Home Screen launch) has nothing to pop —
    // router.back() would leave the app instead of going up a level. The push
    // carries its type, and PageTransition animates it as a pop.
    if (getDepth() === 0) {
      router.push(parentPath(pathname), { transitionTypes: ["nav-back"] });
      return;
    }
    // router.back() is a popstate, and Next renders popstate outside a React
    // transition — so <ViewTransition> never fires for it, and the back button
    // swapped pages with no animation at all. Running the view transition by
    // hand restores the pop. React names nothing here, so the whole screen
    // moves as one snapshot; globals.css animates it under "nav-pop".
    try {
      document.startViewTransition({
        types: ["nav-pop"],
        update: () =>
          new Promise<void>((resolve) => {
            const timer = window.setTimeout(resolve, POP_WAIT);
            popped.current = () => {
              window.clearTimeout(timer);
              resolve();
            };
            router.back();
          }),
      });
    } catch {
      // No view transitions, or none with types: a plain pop.
      router.back();
    }
  };

  return (
    <header className="navbar" data-collapsed={collapsed} data-compact={isArticle}>
      <div className="navbar__bar">
        <div className="navbar__side">
          {back && (
            <button type="button" className="navbar__back" onClick={goBack}>
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="m15 5-7 7 7 7" />
              </svg>
              <span>{back}</span>
            </button>
          )}
        </div>
        <span className="navbar__title">
          {isArticle ? articleTitle : title}
        </span>
        <div className="navbar__side navbar__side--end">
          <StoryModeToggle />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

// The large title sits in normal flow, outside the sticky bar, so it scrolls
// away with the content instead of being animated. Nothing here changes
// layout during scroll, which is what keeps the collapse smooth.
//
// It lives in the layout, so it never enters or exits on its own; keying it by
// route makes each page's title a new instance that slides with the page it
// heads. Left out, it cross-faded in place while the content beneath it slid.
export function LargeTitle() {
  const pathname = usePathname() ?? "/";
  if (pathname.startsWith("/post/")) return null;
  const { title } = titleFor(pathname);
  return (
    <ViewTransition key={pathname} enter={PAGE_ENTER} exit={PAGE_EXIT} default="none">
      {/* Home's title is the masthead, set like Instagram's wordmark. */}
      <div className="largetitle" data-home={pathname === "/" ? "" : undefined}>
        <h1 className="largetitle__text">{title}</h1>
      </div>
    </ViewTransition>
  );
}
