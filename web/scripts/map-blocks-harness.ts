/**
 * Test harness: run Notion blocks through the site's own mapper and print the
 * result as JSON. Used by shared/tests/test_blocks_parity.py to prove that
 * shared/blocks.py produces byte-identical output.
 *
 *   echo '<blocks json>' | npx tsx scripts/map-blocks-harness.ts
 *
 * Input is the *outgoing* block shape the generators build, where toggle and
 * callout children are inline on block[type].children. mapBlockList expects the
 * API shape, where children are fetched by block id — so ids are synthesised
 * here and resolved from the inline children. That adaptation is the only
 * difference between the two mappers, and pinning it down is the point.
 */

import { mapBlockList } from "../lib/notion-map";

/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Notion echoes back a `plain_text` on every rich-text object it returns, but a
 * block you are about to *send* only carries text.content. lib/notion-map.ts
 * reads plain_text because it only ever sees responses; shared/blocks.py reads
 * text.content because it only ever sees outgoing blocks. Synthesising
 * plain_text here is what Notion itself would do on a write-then-read, and
 * without it the two mappers are being fed different inputs, not compared.
 */
function withPlainText(rt: any): any {
  if (!Array.isArray(rt)) return rt;
  return rt.map((t) =>
    t && typeof t === "object" && t.plain_text === undefined
      ? { ...t, plain_text: t?.text?.content ?? "" }
      : t
  );
}

function prepare(raw: any[], prefix = "b"): { blocks: any[]; children: Map<string, any[]> } {
  const children = new Map<string, any[]>();
  const blocks = raw.map((b, i) => {
    const id = `${prefix}-${i}`;
    const type = b?.type;
    const inline = (b?.[type]?.children ?? b?.children ?? []) as any[];
    if (inline.length) {
      const nested = prepare(inline, id);
      children.set(id, nested.blocks);
      for (const [k, v] of nested.children) children.set(k, v);
    }

    const body = type ? b?.[type] : undefined;
    const normalised =
      body && typeof body === "object"
        ? {
            ...body,
            ...(body.rich_text ? { rich_text: withPlainText(body.rich_text) } : {}),
            ...(body.caption ? { caption: withPlainText(body.caption) } : {}),
          }
        : body;

    return { ...b, ...(type ? { [type]: normalised } : {}), id, has_children: inline.length > 0 };
  });
  return { blocks, children };
}

async function main(): Promise<void> {
  const stdin = await new Promise<string>((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });

  const raw = JSON.parse(stdin);
  const { blocks, children } = prepare(raw);
  const mapped = await mapBlockList(blocks, async (id) => children.get(id) ?? []);
  process.stdout.write(JSON.stringify(mapped, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
