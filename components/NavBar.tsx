"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Search from "@/components/Search";
import StoryModeToggle from "@/components/StoryModeToggle";
import ThemeToggle from "@/components/ThemeToggle";
import { getSection, SITE } from "@/lib/config";
import { getDepth, markDirection, parentPath } from "@/lib/nav";

// Scroll distance after which the large title has fully collapsed into the bar.
const COLLAPSE_AT = 44;

function titleFor(pathname: string): { title: string; back: string | null } {
  if (pathname.startsWith("/post/")) {
    const key = pathname.split("/")[2] ?? "";
    return { title: getSection(key)?.label ?? SITE.name, back: getSection(key)?.label ?? "Back" };
  }
  if (pathname.startsWith("/section/")) {
    const key = pathname.split("/")[2] ?? "";
    return { title: getSection(key)?.title ?? SITE.name, back: null };
  }
  if (pathname === "/offline") return { title: "Offline", back: "Back" };
  return { title: SITE.name, back: null };
}

export default function NavBar() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [articleTitle, setArticleTitle] = useState("");

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
    markDirection("pop");
    // A cold entry (shared link, Home Screen launch) has nothing to pop —
    // router.back() would leave the app instead of going up a level.
    if (getDepth() > 0) router.back();
    else router.push(parentPath(pathname));
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
          <Search />
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
export function LargeTitle() {
  const pathname = usePathname() ?? "/";
  if (pathname.startsWith("/post/")) return null;
  const { title } = titleFor(pathname);
  return (
    <div className="largetitle">
      <h1 className="largetitle__text">{title}</h1>
    </div>
  );
}
