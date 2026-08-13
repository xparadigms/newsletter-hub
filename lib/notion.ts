import { Client } from "@notionhq/client";
import { unstable_cache } from "next/cache";
import { cache } from "react";
import { SECTIONS } from "./config";
import type { Block, Post, PostDetail, SectionKey } from "./types";

// Data layer over the four Notion newsletter databases. Requires NOTION_TOKEN;
// without it the site renders with empty sections and a banner.

const token = process.env.NOTION_TOKEN;
const notion = token ? new Client({ auth: token }) : null;

export const notionConnected = Boolean(token);

/* eslint-disable @typescript-eslint/no-explicit-any */

// Assembling an issue takes ~45 Notion calls. Notion tolerates short bursts but
// throttles sustained load, so allow parallelism while capping it, and retry on
// 429 — an unretried rate limit looks like "missing page" and bakes in a 404.
const MAX_CONCURRENT = 4;
let active = 0;
const waiting: (() => void)[] = [];

async function throttle<T>(fn: () => Promise<T>): Promise<T> {
  if (active >= MAX_CONCURRENT) {
    await new Promise<void>((resolve) => waiting.push(resolve));
  }
  active++;
  try {
    return await fn();
  } finally {
    active--;
    waiting.shift()?.();
  }
}

function isTransient(err: any): boolean {
  const status = err?.status;
  if (status === 429 || status >= 500) return true;
  // SDK timeouts and socket errors carry a code and no status, so checking
  // status alone mistook them for permanent failures.
  const code = err?.code;
  return (
    code === "rate_limited" ||
    code === "service_unavailable" ||
    code === "internal_server_error" ||
    code === "notionhq_client_request_timeout" ||
    code === "notionhq_client_response_error" ||
    code === "ECONNRESET" ||
    code === "ETIMEDOUT" ||
    code === "UND_ERR_CONNECT_TIMEOUT" ||
    code === "UND_ERR_HEADERS_TIMEOUT" ||
    err?.name === "RequestTimeoutError" ||
    err?.name === "AbortError"
  );
}

// Only Notion saying "no such page" counts as missing. Anything else must
// propagate: unstable_cache would otherwise store null and keep serving a
// "Not found" page for an issue that exists.
function isMissing(err: any): boolean {
  const code = err?.code;
  return (
    code === "object_not_found" ||
    code === "validation_error" ||
    err?.status === 404
  );
}

async function call<T>(fn: () => Promise<T>, attempts = 3): Promise<T> {
  for (let i = 0; ; i++) {
    try {
      return await throttle(fn);
    } catch (err) {
      if (i >= attempts - 1 || !isTransient(err)) throw err;
      await new Promise((r) => setTimeout(r, 400 * 2 ** i));
    }
  }
}

function richText(rt: any[] | undefined): string {
  return (rt ?? []).map((t) => t?.plain_text ?? "").join("");
}

// Titles follow "[Series #N] (Headline)" or "[Series #N] Headline"; split the
// series label out so lists stay scannable.
function parseTitle(raw: string): { title: string; series: string | null } {
  const m = raw.match(/^\[([^\]]+)\]\s*([\s\S]*)$/);
  if (!m) return { title: raw, series: null };
  let rest = m[2].trim();
  const paren = rest.match(/^\(([\s\S]*)\)$/);
  if (paren) rest = paren[1].trim();
  return { title: rest || raw, series: m[1].trim() };
}

function mapPage(page: any, section: SectionKey): Post {
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

// database id → data source id is immutable; avoid re-resolving per query.
const dataSourceIds = new Map<string, string>();

async function getDataSourceId(databaseId: string): Promise<string> {
  const cached = dataSourceIds.get(databaseId);
  if (cached) return cached;
  const db: any = await call(() =>
    notion!.databases.retrieve({ database_id: databaseId })
  );
  const id = db?.data_sources?.[0]?.id ?? databaseId;
  dataSourceIds.set(databaseId, id);
  return id;
}

async function fetchPosts(section: SectionKey): Promise<Post[]> {
  if (!notion) return [];
  const config = SECTIONS.find((s) => s.key === section)!;
  try {
    const dataSourceId = await getDataSourceId(config.notionId);
    const posts: Post[] = [];
    let cursor: string | undefined;
    do {
      const res: any = await call(() =>
        (notion as any).dataSources.query({
          data_source_id: dataSourceId,
          page_size: 100,
          start_cursor: cursor,
          sorts: [{ property: "Date", direction: "descending" }],
        })
      );
      posts.push(
        ...(res.results ?? [])
          .filter((r: any) => r.object === "page")
          .map((p: any) => mapPage(p, section))
      );
      cursor = res.has_more ? res.next_cursor : undefined;
    } while (cursor && posts.length < 500);
    return posts;
  } catch (err) {
    console.error(`Failed to load Notion posts for ${section}:`, err);
    return [];
  }
}

// Shared across home, section, and article routes so each ISR revalidation
// queries Notion once per section instead of once per page.
export const getPosts = unstable_cache(fetchPosts, ["posts", "v2"], {
  revalidate: 300,
});

export async function getAllPosts(): Promise<Record<SectionKey, Post[]>> {
  const [startup, fintech, japan, watch] = await Promise.all([
    getPosts("startup"),
    getPosts("fintech"),
    getPosts("japan"),
    getPosts("watch"),
  ]);
  return { startup, fintech, japan, watch };
}

async function listChildren(blockId: string): Promise<any[]> {
  const results: any[] = [];
  let cursor: string | undefined;
  do {
    const res: any = await call(() =>
      notion!.blocks.children.list({
        block_id: blockId,
        page_size: 100,
        start_cursor: cursor,
      })
    );
    results.push(...(res.results ?? []));
    cursor = res.has_more ? res.next_cursor : undefined;
  } while (cursor);
  return results;
}

async function mapBlocks(raw: any[], depth = 0): Promise<Block[]> {
  // Toggles/callouts keep their bodies in child blocks; fetch one level down.
  const childLists = await Promise.all(
    raw.map((b) =>
      b.has_children && depth < 2 && (b.type === "toggle" || b.type === "callout")
        ? listChildren(b.id).then((c) => mapBlocks(c, depth + 1))
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

async function fetchPost(
  id: string,
  section: SectionKey
): Promise<PostDetail | null> {
  if (!notion) return null;
  try {
    const [page, children] = await Promise.all([
      call(() => notion!.pages.retrieve({ page_id: id })),
      listChildren(id),
    ]);
    const post = mapPage(page, section);
    return { ...post, blocks: await mapBlocks(children) };
  } catch (err) {
    // Only a genuinely missing page may be cached as "not found".
    if (!isMissing(err)) throw err;
    console.error(`Notion page ${id} not found:`, err);
    return null;
  }
}

// An issue costs ~45 Notion calls (one per furigana toggle), so the result is
// cached across requests, not just deduped within one render.
const cachedPost = unstable_cache(fetchPost, ["post", "v2"], {
  revalidate: 300,
});

// React cache() additionally dedupes the generateMetadata + page-component
// calls within a single render.
export const getPost = cache(
  (id: string, section: SectionKey): Promise<PostDetail | null> =>
    cachedPost(id, section)
);
