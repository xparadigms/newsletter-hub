// A cold issue takes seconds to assemble from Notion. Without this the story
// route showed a blank black screen for that whole time.
export default function Loading() {
  return (
    <div className="story-root">
      <div className="story-progress" aria-hidden>
        {Array.from({ length: 8 }).map((_, i) => (
          <span key={i} className="story-progress__seg" data-state="todo" />
        ))}
      </div>
      <div className="story-topbar">
        <span className="story-skeleton__line story-skeleton__line--label" />
      </div>
      <div className="story-stage">
        <div className="story-card story-card--cover">
          <span className="story-skeleton__line story-skeleton__line--label" />
          <span className="story-skeleton__line story-skeleton__line--title" />
          <span className="story-skeleton__line story-skeleton__line--title story-skeleton__line--short" />
          <div className="story-skeleton__deck">
            {Array.from({ length: 3 }).map((_, i) => (
              <span
                key={i}
                className={`story-skeleton__line${i === 2 ? " story-skeleton__line--short" : ""}`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
