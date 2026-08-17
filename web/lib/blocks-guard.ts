import type { Block, PinyinWord } from "./types";

// Runtime validation for Block[], and the reason a second producer can't drift.
//
// Four generators build blocks by mapping Notion, which shared/blocks.py and
// lib/notion-map.ts keep in lockstep via a parity test. China builds Block[]
// natively in Python instead — no Notion involved — so nothing structural ties
// it to this union. This guard is that tie: the exhaustive switch means adding a
// variant without teaching it is a compile error, and scripts/validate-blocks.ts
// turns it into a check the Python side can run over real output.

const isString = (v: unknown): v is string => typeof v === "string";

export function isBlock(value: unknown): value is Block {
  if (!value || typeof value !== "object") return false;
  const block = value as { type?: unknown };

  switch (block.type as Block["type"]) {
    case "paragraph":
    case "quote":
      return isString((block as { text: unknown }).text);

    case "heading": {
      const h = block as { level: unknown; text: unknown };
      return isString(h.text) && (h.level === 1 || h.level === 2 || h.level === 3);
    }

    case "list": {
      const l = block as { ordered: unknown; items: unknown };
      return (
        typeof l.ordered === "boolean" &&
        Array.isArray(l.items) &&
        l.items.every(isString)
      );
    }

    case "callout":
    case "toggle": {
      const c = block as { text: unknown; children: unknown };
      return (
        isString(c.text) && Array.isArray(c.children) && c.children.every(isBlock)
      );
    }

    case "code": {
      const c = block as { text: unknown; language: unknown };
      return isString(c.text) && isString(c.language);
    }

    case "image": {
      const img = block as { url: unknown; caption: unknown };
      return isString(img.url) && isString(img.caption);
    }

    case "pinyin": {
      const p = block as { words: unknown };
      return (
        Array.isArray(p.words) &&
        p.words.every(
          (w: PinyinWord) =>
            !!w &&
            typeof w === "object" &&
            isString(w.text) &&
            (w.pinyin === undefined || isString(w.pinyin))
        )
      );
    }

    case "divider":
      return true;

    default: {
      // Adding a Block variant without a case above fails to compile here.
      const exhaustive: never = block.type as never;
      return exhaustive;
    }
  }
}

/** Every invalid block, described by index. Empty means the list is valid. */
export function findInvalidBlocks(blocks: unknown): string[] {
  if (!Array.isArray(blocks)) return ["top level is not an array"];
  const problems: string[] = [];
  blocks.forEach((b, i) => {
    if (!isBlock(b)) {
      const type = (b as { type?: unknown })?.type;
      problems.push(`[${i}] invalid ${typeof type === "string" ? type : "block"}`);
    }
  });
  return problems;
}
