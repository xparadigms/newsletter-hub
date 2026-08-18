import { Fragment } from "react";
import type { AnnotatedBlock, RubySegment } from "@/lib/text";
import type { Block, PinyinWord } from "@/lib/types";

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

// A Chinese sentence as word units: pinyin over the base via native <ruby>, and
// the rule under each unit via border-bottom on the wrapper.
//
// The wrappers are `display: inline`, not `inline-block`. An inline-block is an
// atomic inline, which CSS Text substitutes with U+FFFC — line-break class CB,
// which permits a break on BOTH sides unconditionally. Because the real
// characters are then hidden from the algorithm, the rule forbidding a line to
// start with 。 and the rule binding a number to what follows both stop applying.
// That is what orphaned 。 onto its own line and split 诞辰100 from 周年. As
// plain inlines the browser sees one character stream again, and `white-space:
// nowrap` is what keeps a word from splitting inside itself.
//
// border-bottom, not text-decoration: underline — decoration propagates into
// descendants and would draw a line through the <rt> as well. Borders do not
// inherit.
export function renderPinyin(words: PinyinWord[], i: number): React.ReactNode {
  const out: React.ReactNode[] = [];
  let bare = "";
  const flush = () => {
    if (bare) {
      out.push(bare);
      bare = "";
    }
  };

  let lastWasWord = false;
  words.forEach((w, j) => {
    if (!w.pinyin) {
      // Punctuation and bare numerals become text nodes, not spans: they need no
      // rule and no wrapper, and leaving them as real characters is what lets
      // the browser apply its own rules to them. Consecutive ones concatenate so
      // React never emits two adjacent text children.
      bare += w.text;
      lastWasWord = false;
      return;
    }
    flush();
    // An explicit break opportunity between two word spans. Each span is
    // white-space: nowrap so a word never splits, and React emits them with no
    // text node between — which left the browser nowhere to break the line at
    // all, so a sentence became one unbreakable run that overflowed the screen
    // and dragged the card's width with it. <wbr> says "here is a break
    // opportunity" without depending on how an engine resolves white-space at
    // the boundary between two elements.
    if (lastWasWord) out.push(<wbr key={`b${j}`} />);
    out.push(
      <span key={j} className="pinyin__w">
        <ruby>
          {w.text}
          <rt>{w.pinyin}</rt>
        </ruby>
      </span>
    );
    lastWasWord = true;
  });
  flush();

  return (
    <p key={i} className="pinyin" lang="zh-Hans">
      {out}
    </p>
  );
}

// A leading "1." on a story heading renders in gold. Split rather than styled
// with ::before so the number stays in the text for the TOC and for search.
const ORDINAL = /^(\d{1,2}\.)\s+/;

export function headingContent(text: string): React.ReactNode {
  const m = text.match(ORDINAL);
  if (!m) return text;
  return (
    <>
      <span className="heading__num">{m[1]}</span> {text.slice(m[0].length)}
    </>
  );
}

export function renderBlock(block: Block, i: number): React.ReactNode {
  switch (block.type) {
    case "paragraph":
      return <p key={i}>{block.text}</p>;
    case "heading": {
      const Tag = (`h${block.level + 1}`) as "h2" | "h3" | "h4";
      return <Tag key={i}>{headingContent(block.text)}</Tag>;
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
    case "pinyin":
      return renderPinyin(block.words, i);
    case "divider":
      return <hr key={i} />;
    default: {
      // renderBlock returns ReactNode, and undefined is assignable to it — so a
      // Block variant with no case here compiles clean and renders nothing at
      // all. This turns that into a build failure.
      const exhaustive: never = block;
      return exhaustive;
    }
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
        {headingContent(a.block.text)}
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
