"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PrefetchLink from "@/components/PrefetchLink";
import { getSection, NAV_SECTIONS } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";

interface Entry {
  i: string; // id
  s: string; // section
  t: string; // title
  d: string | null; // date
  r: string | null; // series
}

const CACHE_KEY = "search-index-v2";
const LIMIT = 50;

// The Search tab. The whole archive's titles come down once (~25KB, cached for
// the visit) and are filtered here, so typing never waits on the network.
export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<Entry[] | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      const cached = sessionStorage.getItem(CACHE_KEY);
      if (cached) {
        setIndex(JSON.parse(cached));
        return;
      }
    } catch {}
    fetch("/api/search")
      .then((r) => r.json())
      .then((data: Entry[]) => {
        setIndex(data);
        try {
          sessionStorage.setItem(CACHE_KEY, JSON.stringify(data));
        } catch {}
      })
      .catch(() => setIndex([]));
  }, []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !index) return [];
    return index
      .filter((e) => {
        const label = getSection(e.s)?.label ?? "";
        return (
          e.t.toLowerCase().includes(q) ||
          (e.r ?? "").toLowerCase().includes(q) ||
          label.toLowerCase().includes(q)
        );
      })
      .slice(0, LIMIT);
  }, [query, index]);

  return (
    <div className="container search-page">
      <label className="search-field">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" aria-hidden>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.6-3.6" />
        </svg>
        <input
          ref={input}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search every issue"
          aria-label="Search every issue"
          enterKeyHint="search"
        />
      </label>

      {!query.trim() ? (
        <>
          <span className="label inset-list__header">Sections</span>
          <ul className="inset-list">
            {NAV_SECTIONS.map((s) => (
              <li key={s.key}>
                <PrefetchLink href={`/section/${s.key}`} className="search-row" transitionTypes={["nav-forward"]}>
                  <span className="search-row__title">{s.title}</span>
                  <span className="post-row__arrow" aria-hidden />
                </PrefetchLink>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <ul className="inset-list">
          {results.map((e) => (
            <li key={`${e.s}/${e.i}`}>
              <PrefetchLink href={`/post/${e.s}/${e.i}`} className="search-row" transitionTypes={["nav-forward"]}>
                <span className="search-row__text">
                  <span className="label">
                    {getSection(e.s)?.label} · {formatShortDate(e.d)}
                  </span>
                  <span className="search-row__title">{e.t}</span>
                </span>
                <span className="post-row__arrow" aria-hidden />
              </PrefetchLink>
            </li>
          ))}
          {results.length === 0 && (
            <li className="search-row search-row--empty">{index ? "No issues match" : "Loading…"}</li>
          )}
        </ul>
      )}
    </div>
  );
}
