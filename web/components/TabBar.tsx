"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// The app's four tabs, as in the iOS app. The sections themselves live one
// level down, under Sections — eight of them never fitted a phone-width bar.
const ICONS: Record<string, React.ReactNode> = {
  home: <path d="M3.5 10.5 12 4l8.5 6.5V20a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1z" />,
  sections: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" fill="none" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8.5" r="3.8" />
      <path d="M4.5 20c.9-3.6 3.9-5.6 7.5-5.6s6.6 2 7.5 5.6" />
    </>
  ),
};

function TabIcon({ name, active }: { name: string; active: boolean }) {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      aria-hidden
      fill={active && name !== "search" ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={active ? 2.1 : 1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONS[name]}
    </svg>
  );
}

const TABS = [
  { key: "home", href: "/", label: "Home" },
  { key: "sections", href: "/sections", label: "Sections" },
  { key: "search", href: "/search", label: "Explore" },
  { key: "profile", href: "/profile", label: "Profile" },
];

// Scrolling down past this tucks the bar away; any upward scroll brings it
// back. The threshold stops a rubber-band bounce at the top from flickering it.
const TUCK_AFTER = 80;

export default function TabBar() {
  const pathname = usePathname() ?? "/";
  const [minimized, setMinimized] = useState(false);

  // The iOS 26 tab bar gets out of the way while you read and returns the
  // moment you reach for it. Direction, not position: a long article scrolled
  // halfway should still show the bar as soon as the thumb moves up.
  useEffect(() => {
    let last = window.scrollY;
    let frame = 0;
    const update = () => {
      frame = 0;
      const y = window.scrollY;
      const down = y > last && y > TUCK_AFTER;
      const up = y < last || y <= TUCK_AFTER;
      if (down) setMinimized(true);
      else if (up) setMinimized(false);
      last = y;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  // A new page starts with the bar visible, whatever the last one did.
  useEffect(() => {
    setMinimized(false);
  }, [pathname]);

  const isActive = (key: string) => {
    if (key === "home") return pathname === "/";
    // Sections owns everything below it: a section's list and its issues.
    if (key === "sections")
      return pathname === "/sections" || pathname.startsWith("/section/") || pathname.startsWith("/post/");
    return pathname === `/${key}`;
  };

  return (
    <nav className="tabbar" aria-label="Sections" data-minimized={minimized}>
      <ul className="tabbar__list">
        {TABS.map((tab) => {
          const active = isActive(tab.key);
          return (
            <li key={tab.key}>
              <Link
                href={tab.href}
                transitionTypes={["nav-tab"]}
                onClick={(e) => {
                  // Tapping the tab you are already on scrolls back to the
                  // top, as on iOS, rather than reloading the same screen.
                  if (pathname !== tab.href) return;
                  e.preventDefault();
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                className="tabbar__tab"
                data-active={active}
                aria-current={active ? "page" : undefined}
              >
                <TabIcon name={tab.key} active={active} />
                <span className="tabbar__label">{tab.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
