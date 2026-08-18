import Link from "next/link";

export const metadata = { title: "Offline" };

export default function OfflinePage() {
  return (
    <div className="state">
      <div className="container">
        <span className="label">Offline</span>
        <h1 className="state__title">No connection</h1>
        <p className="state__text">
          This issue hasn&rsquo;t been read on this device yet, so there&rsquo;s
          no saved copy. Issues you&rsquo;ve already opened stay available
          offline.
        </p>
        <p className="state__actions">
          <Link href="/" className="arrow-link">
            Back to the front page <span aria-hidden>→</span>
          </Link>
        </p>
      </div>
    </div>
  );
}
