"use client";

// Stateless on purpose: the active icon is chosen by CSS from html[data-theme],
// so server and client HTML always match and there is no mount flicker.
export default function ThemeToggle() {
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Toggle color theme"
      onClick={() => {
        const el = document.documentElement;
        const next = el.getAttribute("data-theme") === "dark" ? "light" : "dark";
        const apply = () => {
          el.setAttribute("data-theme", next);
          // Keep the status bar tint in step with the app theme.
          document
            .querySelector('meta[name="theme-color"]')
            ?.setAttribute("content", next === "dark" ? "#0d0d0d" : "#ffffff");
        };
        // A cross-fade rather than a cut, the way the system appearance
        // changes. Browsers older than view transition types throw on the
        // object form; they get the plain swap.
        try {
          document.startViewTransition({ update: apply, types: ["theme"] });
        } catch {
          apply();
        }
        try {
          localStorage.setItem("theme", next);
        } catch {}
      }}
    >
      <svg
        className="theme-toggle__moon"
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
      <svg
        className="theme-toggle__sun"
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
      </svg>
    </button>
  );
}
