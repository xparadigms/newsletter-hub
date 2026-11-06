"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

/** The filter row above the tab bar on Home and Feed. The chosen chip is
 *  scrolled into view, or a filter picked past the edge would look unset. */
export default function FilterBar({
  base,
  options,
  current,
}: {
  base: string;
  options: { key: string; label: string }[];
  current: string | null;
}) {
  const bar = useRef<HTMLElement>(null);
  useEffect(() => {
    bar.current?.querySelector<HTMLElement>('[data-on="true"]')?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [current]);
  return (
    <nav ref={bar} className="filterbar" aria-label="Newsletter">
      <Link href={base} className="chip" data-on={!current} replace scroll={false}>
        All
      </Link>
      {options.map((o) => (
        <Link key={o.key} href={`${base}?s=${o.key}`} className="chip" data-on={current === o.key} replace scroll={false}>
          {o.label}
        </Link>
      ))}
    </nav>
  );
}
