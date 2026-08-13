import { Fragment } from "react";
import type { AnnotatedBlock, RubySegment } from "@/lib/text";
import type { Block } from "@/lib/types";

// Shared between the article page and story mode so both render Notion blocks
// — including furigana ruby and the language wrappers — identically.

export function renderRuby(segments: RubySegment[]): React.ReactNode {
  return segments.map((s, i) =>
    s.reading ? (
      <ruby key={i}>
        {s.text}
        <rt>{s.reading}</rt>
      </ruby>
    ) : (
      <Fragment key={i}>{s.text}</Fragment>
    )
  );
}

export function renderBlock(block: Block, i: number): React.ReactNode {
  switch (block.type) {
    case "paragraph":
      return <p key={i}>{block.text}</p>;
    case "heading": {
      const Tag = (`h${block.level + 1}`) as "h2" | "h3" | "h4";
      return <Tag key={i}>{block.text}</Tag>;
    }
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag key={i}>
          {block.items.map((item, j) => (
            <li key={j}>{item}</li>
          ))}
        </Tag>
      );
    }
    case "quote":
      return <blockquote key={i}>{block.text}</blockquote>;
    case "callout":
      return (
        <div key={i} className="callout">
          {block.text && <span className="callout__label">{block.text}</span>}
          {block.children.map(renderBlock)}
        </div>
      );
    case "toggle":
      return (
        <details key={i} className="toggle">
          <summary>{block.text}</summary>
          {block.children.map(renderBlock)}
        </details>
      );
    case "code":
      return (
        <pre key={i}>
          <code>{block.text}</code>
        </pre>
      );
    case "image":
      return (
        <figure key={i}>
          {/* Notion file URLs are short-lived signed URLs; plain img avoids next/image domain config */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={block.url} alt={block.caption || ""} />
          {block.caption && <figcaption>{block.caption}</figcaption>}
        </figure>
      );
    case "divider":
      return <hr key={i} />;
  }
}

export function renderAnnotated(a: AnnotatedBlock, i: number): React.ReactNode {
  if (a.kicker && a.block.type === "paragraph") {
    return (
      <p key={i} className="kicker">
        {a.block.text}
      </p>
    );
  }
  if (a.ruby) {
    // Keep the bullet when the annotated sentence was written as a list item.
    const asList = a.block.type === "list";
    return (
      <div key={i} className="lang-wrap" data-lang="ja" lang="ja">
        {asList ? (
          <ul>
            <li className="has-ruby">{renderRuby(a.ruby)}</li>
          </ul>
        ) : (
          <p className="has-ruby">{renderRuby(a.ruby)}</p>
        )}
      </div>
    );
  }
  if (a.block.type === "heading" && a.headingId) {
    const Tag = (`h${a.block.level + 1}`) as "h2" | "h3" | "h4";
    return (
      <Tag key={i} id={a.headingId}>
        {a.block.text}
      </Tag>
    );
  }
  // Structural blocks (lang null) render bare and are never filtered.
  if (a.lang === null) return renderBlock(a.block, i);
  return (
    <div
      key={i}
      className="lang-wrap"
      data-lang={a.lang}
      lang={a.lang === "en" ? undefined : a.lang}
    >
      {renderBlock(a.block, 0)}
    </div>
  );
}
