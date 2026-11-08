"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getSection } from "@/lib/config";
import { MODE_COOKIE, MODES, type Mode } from "@/lib/mode";

/** Stores the mode and re-renders the page's lists for it. A section filter
 *  (?s=) belongs to the old mode, so it is dropped. */
function useSetMode() {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  return (mode: Mode) => {
    document.cookie = `${MODE_COOKIE}=${mode}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.setAttribute("data-mode", mode);
    router.replace(pathname, { scroll: false });
    router.refresh();
  };
}

// The flags and checkmarks are chosen by CSS from html[data-mode], which the
// boot script sets before first paint, so server and client HTML match and
// the title never shows the wrong flag on load.
function Flags() {
  return (
    <>
      {MODES.map((m) => (
        <span key={m.key} className="mode-flag" data-flag={m.key} aria-hidden>
          {m.flag}
        </span>
      ))}
    </>
  );
}

/** Home's masthead: "The Brief 🇯🇵 ⌄", where Instagram puts its account
 *  switcher, opening a menu of the two modes. */
export function ModeTitle({ title }: { title: string }) {
  const setMode = useSetMode();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="mode-title" ref={root}>
      <button
        type="button"
        className="mode-title__button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${title}. Switch between Japan and China mode`}
        onClick={() => setOpen((o) => !o)}
      >
        <h1 className="largetitle__text">{title}</h1>
        <Flags />
        <svg className="mode-title__chevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <ul className="mode-menu" role="menu">
          {MODES.map((m) => (
            <li key={m.key}>
              <button
                type="button"
                role="menuitem"
                className="mode-menu__item"
                data-mode-option={m.key}
                onClick={() => {
                  setOpen(false);
                  setMode(m.key);
                }}
              >
                <span className="mode-menu__flag" aria-hidden>{m.flag}</span>
                <span className="mode-menu__text">
                  <span className="mode-menu__title">{m.title}</span>
                  <span className="mode-menu__desc">{m.sections.map((k) => getSection(k)?.label ?? k).join(", ")}</span>
                </span>
                <svg className="mode-menu__check" width="16" height="16" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="m5 12.5 4.5 4.5L19 7.5" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The segmented control at the top of Sections, as in the app. */
export function ModeSegmented({ current }: { current: Mode }) {
  const setMode = useSetMode();
  return (
    <div className="mode-segmented" role="radiogroup" aria-label="Mode">
      {MODES.map((m) => (
        <button
          key={m.key}
          type="button"
          role="radio"
          aria-checked={current === m.key}
          data-on={current === m.key}
          className="mode-segmented__option"
          onClick={() => current !== m.key && setMode(m.key)}
        >
          {m.flag} {m.title}
        </button>
      ))}
    </div>
  );
}
