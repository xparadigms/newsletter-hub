"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SECTIONS } from "@/lib/config";

// Simple, legible glyphs in the SF Symbols spirit: outline when inactive, the
// same shape filled when active.
function Glyph({ name, active }: { name: string; active: boolean }) {
  const stroke = {
    fill: active ? "currentColor" : "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden {...stroke}>
      {name === "home" && <path d="M3.5 10.5 12 4l8.5 6.5V20a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1z" />}
      {name === "startup" && <path d="M12 3c3 2.2 4.6 5.2 4.6 8.6L18 14v3l-3-1.2h-6L6 17v-3l1.4-2.4C7.4 8.2 9 5.2 12 3Z" />}
      {name === "fintech" && <path d="M4 19V9m5 10V5m5 14v-7m5 7V8" />}
      {name === "japan" && <path d="M12 21c4-3.4 7-6.9 7-10.5A7 7 0 1 0 5 10.5C5 14.1 8 17.6 12 21Z" />}
      {name === "watch" && (
        <>
          <circle cx="12" cy="12" r="6" />
          <path d="M12 9.5V12l1.7 1.2" fill="none" />
        </>
      )}
    </svg>
  );
}

const TABS = [
  { key: "home", href: "/", label: "Today", glyph: "home" },
  ...SECTIONS.map((s) => ({
    key: s.key,
    href: `/section/${s.key}`,
    label: s.label,
    glyph: s.key,
  })),
];

export default function TabBar() {
  const pathname = usePathname() ?? "/";

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    // Keep the owning tab lit while reading one of its articles.
    const key = href.split("/").pop()!;
    return pathname === href || pathname.startsWith(`/post/${key}/`);
  };

  return (
    <nav className="tabbar" aria-label="Sections">
      <ul className="tabbar__list">
        {TABS.map((tab) => {
          const active = isActive(tab.href);
          return (
            <li key={tab.key}>
              <Link
                href={tab.href}
                className="tabbar__tab"
                data-active={active}
                aria-current={active ? "page" : undefined}
              >
                <Glyph name={tab.glyph} active={active} />
                <span className="tabbar__label">{tab.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
