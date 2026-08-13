"use client";

// Stateless segmented control; active state is CSS-driven from html[data-langs]
// (restored pre-paint by the inline script in layout.tsx), so there is no
// hydration mismatch and no layout shift on load.
export default function LangToggle() {
  const set = (value: string) => {
    document.documentElement.setAttribute("data-langs", value);
    try {
      localStorage.setItem("langs", value);
    } catch {}
  };

  return (
    <span className="lang-toggle" role="group" aria-label="Reading language">
      <button type="button" data-value="ja-ko" onClick={() => set("ja-ko")}>
        日本語 · 한국어
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
