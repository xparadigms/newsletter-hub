// Shown instantly while an older issue is assembled from Notion for the first
// time. Once rendered it is cached, so this is a first-visit-only state.
export default function Loading() {
  return (
    <article className="article">
      <div className="article__col skeleton">
        <div className="skeleton__line skeleton__line--label" />
        <div className="skeleton__line skeleton__line--title" />
        <div className="skeleton__line skeleton__line--title skeleton__line--short" />
        <div className="skeleton__body">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className={`skeleton__line${i % 4 === 3 ? " skeleton__line--short" : ""}`}
            />
          ))}
        </div>
      </div>
    </article>
  );
}
