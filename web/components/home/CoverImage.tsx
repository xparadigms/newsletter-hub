"use client";

import { useState } from "react";
import type { Cover } from "@/lib/types";

/** An issue's cover photo. Hotlinked from where the story came from, so it
 *  sends no referrer (some publishers refuse hotlinks that carry one), and
 *  if it will not load it simply goes, leaving the typographic card. */
export default function CoverImage({
  cover,
  className,
  eager = false,
}: {
  cover: Cover | null | undefined;
  className?: string;
  eager?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (!cover?.url || failed) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={cover.url}
      alt=""
      className={className}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      draggable={false}
    />
  );
}

/** "Photo: techcrunch.com", linked to where it came from. */
export function CoverCredit({ cover, className }: { cover: Cover | null | undefined; className?: string }) {
  if (!cover?.url) return null;
  return (
    <a href={cover.link} className={className} target="_blank" rel="noopener noreferrer">
      Photo: {cover.credit}
    </a>
  );
}
