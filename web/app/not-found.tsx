import Link from "next/link";

export const metadata = { title: "Not found" };

export default function NotFound() {
  return (
    <div className="page-head">
      <div className="container">
        <span className="label">404</span>
        <h1 className="state__title">This page doesn&rsquo;t exist</h1>
        <p>
          The issue may have been moved or unpublished. Everything still
          available is listed on the front page.
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
