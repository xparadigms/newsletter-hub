"use client";

import Link from "next/link";

// Reading an issue can fail transiently when Notion rate-limits us. That is
// worth retrying in place rather than sending the reader away.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="state">
      <div className="container">
        <span className="label">Something went wrong</span>
        <h1 className="state__title">This didn&rsquo;t load</h1>
        <p>
          The newsletter source may be busy. Trying again usually works — issues
          you&rsquo;ve already opened stay available offline.
        </p>
        <p className="state__actions">
          <button type="button" className="state__retry" onClick={reset}>
            Try again
          </button>
          <Link href="/" className="arrow-link">
            Front page <span aria-hidden>→</span>
          </Link>
        </p>
        {error.digest && <span className="label">Ref {error.digest}</span>}
      </div>
    </div>
  );
}
