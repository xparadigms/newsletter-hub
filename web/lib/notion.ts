import { Client } from "@notionhq/client";
import { unstable_cache } from "next/cache";
import { cache } from "react";
import { SECTIONS } from "./config";
import { mapBlockList, mapPage } from "./notion-map";
import type { Post, PostDetail, SectionKey } from "./types";

// Data layer over the four Notion newsletter databases. Requires NOTION_TOKEN;
// without it the site renders with empty sections and a banner.

const token = process.env.NOTION_TOKEN;
const notion = token ? new Client({ auth: token }) : null;

export const notionConnected = Boolean(token);

// Cache tags, invalidated on demand by /api/revalidate. Lists expire on a timer
// as well; issue bodies only ever expire through these.
export const POSTS_TAG = "posts";
export const POST_TAG = "post";
export const postTag = (id: string) => `${POST_TAG}:${id}`;

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
  tags: [POSTS_TAG],
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
    return { ...post, blocks: await mapBlockList(children, listChildren) };
  } catch (err) {
    // Only a genuinely missing page may be cached as "not found".
    if (!isMissing(err)) throw err;
    console.error(`Notion page ${id} not found:`, err);
    return null;
  }
}

// An issue costs ~45 Notion calls (one per furigana toggle), so the result is
// cached across requests, not just deduped within one render.
//
// It never expires on a timer. An issue doesn't change after publication, but a
// five-minute TTL threw the assembly away anyway, so every archive issue, every
// deep link, and every issue opened after a quiet spell paid the full ~4s again
// — warming only ever covered the newest handful. Freshness now comes from
// /api/revalidate, which is the only thing that can evict a body.
//
// The wrapper is built per call rather than at module scope so the id can reach
// both the cache key and the tags; that's what makes single-issue invalidation
// possible. The inner function takes no arguments, so ["post", "v3", id] is the
// whole key.
const cachedPost = (id: string, section: SectionKey) =>
  unstable_cache(() => fetchPost(id, section), ["post", "v3", id], {
    revalidate: false,
    tags: [POST_TAG, postTag(id)],
  })();

// React cache() additionally dedupes the generateMetadata + page-component
// calls within a single render.
export const getPost = cache(
  (id: string, section: SectionKey): Promise<PostDetail | null> =>
    cachedPost(id, section)
);
