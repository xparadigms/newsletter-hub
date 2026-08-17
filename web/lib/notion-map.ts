import type { Block, Post, SectionKey } from "./types";

// Pure Notion → domain mappers, with no client, no cache and no I/O of their
// own. They live apart from lib/notion.ts so the Notion→Supabase backfill can
// import them: lib/notion.ts evaluates unstable_cache() at module scope, which
// throws outside a Next server context.
//
// These are the mappers the live site renders with. The backfill reusing them
// verbatim is what makes the migrated archive correct by construction rather
// than correct by inspection.

/* eslint-disable @typescript-eslint/no-explicit-any */

export function richText(rt: any[] | undefined): string {
  return (rt ?? []).map((t) => t?.plain_text ?? "").join("");
}

// Titles follow "[Series #N] (Headline)" or "[Series #N] Headline"; split the
// series label out so lists stay scannable.
export function parseTitle(raw: string): { title: string; series: string | null } {
  const m = raw.match(/^\[([^\]]+)\]\s*([\s\S]*)$/);
  if (!m) return { title: raw, series: null };
  let rest = m[2].trim();
  const paren = rest.match(/^\(([\s\S]*)\)$/);
  if (paren) rest = paren[1].trim();
  return { title: rest || raw, series: m[1].trim() };
}

export function mapPage(page: any, section: SectionKey): Post {
  const props = page.properties ?? {};
  const find = (type: string): any =>
    Object.values(props).find((p: any) => p?.type === type);

  const { title, series } = parseTitle(richText(find("title")?.title) || "Untitled");
  const date =
    find("date")?.date?.start ??
    (page.created_time ? page.created_time.slice(0, 10) : null);
  const summary =
    richText(find("rich_text")?.rich_text).replace(/^-\s*/, "").trim() || null;

  return { id: page.id, section, title, series, date, summary };
}

// Notion blocks → the renderable Block union. `getChildren` is injected so the
// live path can fetch over the network while a test or an offline re-map can
// serve children from an already-materialised payload.
export async function mapBlockList(
  raw: any[],
  getChildren: (blockId: string) => Promise<any[]>,
  depth = 0
): Promise<Block[]> {
  // Toggles/callouts keep their bodies in child blocks; fetch one level down.
  const childLists = await Promise.all(
    raw.map((b) =>
      b.has_children && depth < 2 && (b.type === "toggle" || b.type === "callout")
        ? getChildren(b.id).then((c) => mapBlockList(c, getChildren, depth + 1))
        : Promise.resolve([] as Block[])
    )
  );

  const blocks: Block[] = [];
  raw.forEach((b, i) => {
    const t = b.type;
    const text = richText(b[t]?.rich_text);
    if (t === "paragraph") {
      if (text.trim()) blocks.push({ type: "paragraph", text });
    } else if (t === "heading_1" || t === "heading_2" || t === "heading_3") {
      const level = Number(t.slice(-1)) as 1 | 2 | 3;
      blocks.push({ type: "heading", level, text });
    } else if (t === "bulleted_list_item" || t === "numbered_list_item") {
      const ordered = t === "numbered_list_item";
      const last = blocks[blocks.length - 1];
      if (last?.type === "list" && last.ordered === ordered) last.items.push(text);
      else blocks.push({ type: "list", ordered, items: [text] });
    } else if (t === "quote") {
      blocks.push({ type: "quote", text });
    } else if (t === "callout") {
      blocks.push({ type: "callout", text, children: childLists[i] });
    } else if (t === "toggle") {
      blocks.push({ type: "toggle", text, children: childLists[i] });
    } else if (t === "code") {
      blocks.push({ type: "code", text, language: b.code?.language ?? "" });
    } else if (t === "divider") {
      blocks.push({ type: "divider" });
    } else if (t === "image") {
      const url = b.image?.file?.url ?? b.image?.external?.url;
      if (url) blocks.push({ type: "image", url, caption: richText(b.image?.caption) });
    }
  });
  return blocks;
}
