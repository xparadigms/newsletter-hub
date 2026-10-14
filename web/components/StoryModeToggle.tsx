"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

// Story mode is a reading preference, not a route: with it on, opening any
// issue anywhere in the app lands in the full-screen story instead of the
// article. Rewriting the target on click keeps every list a server component.
export default function StoryModeToggle() {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [on, setOn] = useState(false);

  useEffect(() => {
    setOn(document.documentElement.getAttribute("data-story") === "on");
  }, []);

  useEffect(() => {
    if (!on) return;
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey) return;
      const link = (e.target as HTMLElement).closest?.("a");
      const href = link?.getAttribute("href");
      if (!href?.startsWith("/post/")) return;
      e.preventDefault();
      router.push(href.replace("/post/", "/story/"), {
        transitionTypes: ["nav-present"],
      });
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [on, router]);

  const toggle = () => {
    const next = !on;
    setOn(next);
    document.documentElement.setAttribute("data-story", next ? "on" : "off");
    try {
      localStorage.setItem("story-mode", next ? "on" : "off");
    } catch {}
    // Switching while reading an issue takes you straight to its other form.
    if (next && pathname.startsWith("/post/")) {
      router.push(pathname.replace("/post/", "/story/"), {
        transitionTypes: ["nav-present"],
      });
    } else if (!next && pathname.startsWith("/story/")) {
      router.push(pathname.replace("/story/", "/post/"), {
        transitionTypes: ["nav-dismiss"],
      });
    }
  };

  return (
    <button
      type="button"
      className="story-toggle"
      onClick={toggle}
      aria-pressed={on}
      aria-label="Story mode"
      title="Story mode"
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="7" y="3" width="10" height="18" rx="2.5" />
        <path d="M3.5 8v8M20.5 8v8" />
      </svg>
    </button>
  );
}
