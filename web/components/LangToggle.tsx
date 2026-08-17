"use client";

// Stateless segmented control; active state is CSS-driven from html[data-langs]
// (restored pre-paint by the inline script in layout.tsx), so there is no
// hydration mismatch and no layout shift on load.
// `source` is the label only. The stored value stays "ja-ko" for every section
// because it means "source language + Korean", not a list of languages —
// inventing a "zh-ko" value would invalidate every saved preference and need a
// parallel set of CSS rules for no gain.
export default function LangToggle({ source = "日本語" }: { source?: string }) {
  const set = (value: string) => {
    document.documentElement.setAttribute("data-langs", value);
    try {
      localStorage.setItem("langs", value);
    } catch {}
  };

  return (
    <span className="lang-toggle" role="group" aria-label="Reading language">
      <button type="button" data-value="ja-ko" onClick={() => set("ja-ko")}>
        {source} · 한국어
      </button>
      <button type="button" data-value="en" onClick={() => set("en")}>
        EN
      </button>
      <button type="button" data-value="all" onClick={() => set("all")}>
        ALL
      </button>
    </span>
  );
}
