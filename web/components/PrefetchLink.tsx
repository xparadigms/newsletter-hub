"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ComponentProps } from "react";
import { useRef } from "react";

type Props = Omit<ComponentProps<typeof Link>, "prefetch">;

// A section index can list hundreds of issues, and Next's default prefetch
// fires for every link that scrolls into view — which is why all of these links
// carried prefetch={false}. That spared Notion an archive-wide stampede, but it
// also meant every tap started a cold navigation.
//
// Prefetching on intent is the middle ground. The ~80ms between finger-down and
// finger-up is enough to get the payload in flight, and only the links a reader
// actually reaches for cost anything.
export default function PrefetchLink({
  href,
  onTouchStart,
  onPointerEnter,
  ...rest
}: Props) {
  const router = useRouter();
  const warmed = useRef(false);

  const warm = () => {
    if (warmed.current) return;
    warmed.current = true;
    if (typeof href === "string") router.prefetch(href);
  };

  return (
    <Link
      href={href}
      prefetch={false}
      onTouchStart={(event) => {
        warm();
        onTouchStart?.(event);
      }}
      // Covers the desktop case, where the pointer arrives before the click.
      onPointerEnter={(event) => {
        warm();
        onPointerEnter?.(event);
      }}
      {...rest}
    />
  );
}
