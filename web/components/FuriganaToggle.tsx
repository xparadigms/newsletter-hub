"use client";

// Hide or show the readings above the kanji.
//
// Stateless like LangToggle: the state lives on html[data-furigana], restored
// before first paint by the inline script in layout.tsx, so the readings never
// flash on and then vanish. Nothing here re-renders the article — the CSS
// switches on the attribute, which also means story mode and the article page
// agree without either knowing about the other.

export default function FuriganaToggle() {
  const toggle = () => {
    const el = document.documentElement;
    const next = el.getAttribute("data-furigana") === "off" ? "on" : "off";
    el.setAttribute("data-furigana", next);
    try {
      localStorage.setItem("furigana", next);
    } catch {}
  };

  return (
    <button
      type="button"
      className="furigana-toggle"
      onClick={toggle}
      aria-label="Toggle furigana"
      title="Toggle furigana"
    >
      <span aria-hidden="true">ふりがな</span>
    </button>
  );
}
