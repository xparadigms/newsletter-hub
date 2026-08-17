"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import BottomSheet from "@/components/BottomSheet";
import { getSection } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";

interface Entry {
  i: string; // id
  s: string; // section
  t: string; // title
  d: string | null; // date
  r: string | null; // series
}

const CACHE_KEY = "search-index-v2";
const LIMIT = 25;

export default function Search() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<Entry[] | null>(null);
  const input = useRef<HTMLInputElement>(null);

  // Fetched once per session, then filtered locally so typing stays instant.
  useEffect(() => {
    if (!open || index) return;
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
  }, [open, index]);

  useEffect(() => {
    if (open) input.current?.focus();
    else setQuery("");
  }, [open]);

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
    <>
      <button
        type="button"
        className="search-toggle"
        onClick={() => setOpen(true)}
        aria-label="Search issues"
        title="Search"
      >
        <svg
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.6-3.6" />
        </svg>
      </button>

      <BottomSheet open={open} onClose={() => setOpen(false)} title="Search">
        <input
          ref={input}
          className="search-input"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search every issue…"
          aria-label="Search issues"
        />
        {query.trim() && (
          <ul className="search-results">
            {results.map((e) => (
              <li key={e.i}>
                <Link
                  href={`/post/${e.s}/${e.i}`}
                  prefetch={false}
                  onClick={() => setOpen(false)}
                >
                  <span className="label">
                    {getSection(e.s)?.label} · {formatShortDate(e.d)}
                  </span>
                  <span className="search-results__title">{e.t}</span>
                </Link>
              </li>
            ))}
            {results.length === 0 && (
              <li className="search-results__empty label">
                {index ? "No issues match" : "Loading…"}
              </li>
            )}
          </ul>
        )}
      </BottomSheet>
    </>
  );
}
