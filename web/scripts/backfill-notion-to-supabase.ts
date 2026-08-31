/**
 * One-time migration: copy the Notion archive into Supabase.
 *
 *   npx tsx scripts/backfill-notion-to-supabase.ts --dry-run
 *   npx tsx scripts/backfill-notion-to-supabase.ts --commit
 *   npx tsx scripts/backfill-notion-to-supabase.ts --verify
 *
 *   ... [--section startup|fintech|japan|watch] [--force]
 *
 * Run from web/. Reads NOTION_TOKEN, SUPABASE_URL and SUPABASE_SECRET_KEY from
 * the environment or from web/.env.local.
 *
 * This deliberately imports the site's own mappers from lib/notion-map.ts, so
 * the migrated blocks are produced by the code that renders the live site —
 * correct by construction rather than by inspection. It is also why there is no
 * Python equivalent of this script.
 *
 * Rows land with published = false. Verify, then flip them in one statement.
 */

import { Client } from "@notionhq/client";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SECTIONS } from "../lib/config";
import { mapBlockList, mapPage, richText } from "../lib/notion-map";
import { blockText } from "../lib/text";
import type { Block, Post, SectionKey } from "../lib/types";

/* eslint-disable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

function loadEnvLocal(): void {
  try {
    const raw = readFileSync(join(process.cwd(), ".env.local"), "utf8");
    for (const line of raw.split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
      if (!m) continue;
      const value = m[2].trim().replace(/^["']|["']$/g, "");
      if (!process.env[m[1]]) process.env[m[1]] = value;
    }
  } catch {
    // No .env.local — rely on the ambient environment.
  }
}
loadEnvLocal();

const args = process.argv.slice(2);
const has = (flag: string) => args.includes(flag);
const arg = (flag: string) => {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
};

const COMMIT = has("--commit");
const VERIFY = has("--verify");
const FORCE = has("--force");
const ONLY = arg("--section") as SectionKey | undefined;

const NOTION_TOKEN = process.env.NOTION_TOKEN;
const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "");
const SUPABASE_SECRET_KEY = process.env.SUPABASE_SECRET_KEY;

if (!NOTION_TOKEN) fail("NOTION_TOKEN is not set");
if (!SUPABASE_URL) fail("SUPABASE_URL is not set");
if (!SUPABASE_SECRET_KEY) fail("SUPABASE_SECRET_KEY is not set");
if (ONLY && !SECTIONS.some((s) => s.key === ONLY)) fail(`unknown section: ${ONLY}`);

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(1);
}

const notion = new Client({ auth: NOTION_TOKEN });
// notionId gates this, not the key: china is Supabase-only and has no Notion
// database, so there is nothing here to migrate from.
const sections = SECTIONS.filter((s) => s.notionId && (!ONLY || s.key === ONLY));

// ---------------------------------------------------------------------------
// Notion access — a local copy of lib/notion.ts's throttle+retry, because that
// module evaluates unstable_cache() at import time and cannot load here.
// ---------------------------------------------------------------------------

const MAX_CONCURRENT = 4;
let active = 0;
const waiting: (() => void)[] = [];

async function throttle<T>(fn: () => Promise<T>): Promise<T> {
  if (active >= MAX_CONCURRENT) await new Promise<void>((r) => waiting.push(r));
  active++;
  try {
    return await fn();
  } finally {
    active--;
    waiting.shift()?.();
  }
}

async function call<T>(fn: () => Promise<T>, attempts = 5): Promise<T> {
  for (let i = 0; ; i++) {
    try {
      return await throttle(fn);
    } catch (err: any) {
      const transient = err?.status === 429 || err?.status >= 500 || !err?.status;
      if (i >= attempts - 1 || !transient) throw err;
      await new Promise((r) => setTimeout(r, 500 * 2 ** i));
    }
  }
}

const dataSourceIds = new Map<string, string>();

async function getDataSourceId(databaseId: string): Promise<string> {
  const cached = dataSourceIds.get(databaseId);
  if (cached) return cached;
  const db: any = await call(() => notion.databases.retrieve({ database_id: databaseId }));
  const id = db?.data_sources?.[0]?.id ?? databaseId;
  dataSourceIds.set(databaseId, id);
  return id;
}

/** Every page in a database, oldest first. */
async function listPages(databaseId: string): Promise<any[]> {
  const dataSourceId = await getDataSourceId(databaseId);
  const pages: any[] = [];
  let cursor: string | undefined;
  do {
    const res: any = await call(() =>
      (notion as any).dataSources.query({
        data_source_id: dataSourceId,
        page_size: 100,
        start_cursor: cursor,
        // created_time, not the "Date" property: it exists on every page, and
        // ascending order makes the slug trigger's -2/-3 suffixes deterministic
        // so a partial re-run produces identical URLs.
        sorts: [{ timestamp: "created_time", direction: "ascending" }],
      })
    );
    pages.push(...(res.results ?? []).filter((r: any) => r.object === "page"));
    cursor = res.has_more ? res.next_cursor : undefined;
  } while (cursor);
  return pages;
}

async function listChildren(blockId: string): Promise<any[]> {
  const results: any[] = [];
  let cursor: string | undefined;
  do {
    const res: any = await call(() =>
      notion.blocks.children.list({
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

// ---------------------------------------------------------------------------
// Mapping
// ---------------------------------------------------------------------------

let droppedImages = 0;

/**
 * Notion-hosted images are served from short-lived signed URLs. Rendering one
 * per request is fine; storing one in jsonb makes the expiry permanent. Drop
 * them at ingest and keep only externally-hosted images.
 */
function stripExpiringImages(raw: any[]): any[] {
  return raw.filter((b) => {
    if (b?.type !== "image") return true;
    if (b.image?.external?.url) return true;
    droppedImages++;
    return false;
  });
}

const getChildrenFiltered = async (blockId: string): Promise<any[]> =>
  stripExpiringImages(await listChildren(blockId));

function rawTitleOf(page: any): string {
  const props = page.properties ?? {};
  const titleProp: any = Object.values(props).find((p: any) => p?.type === "title");
  return richText(titleProp?.title) || "Untitled";
}

interface Row {
  section: SectionKey;
  issue_date: string;
  title: string;
  series: string | null;
  raw_title: string;
  issue_number: number | null;
  summary: string | null;
  blocks: Block[];
  plain_text: string;
  notion_page_id: string;
  notion_url: string | null;
  run_key: string;
  published: boolean;
}

async function buildRow(page: any, section: SectionKey): Promise<Row | null> {
  const post: Post = mapPage(page, section);
  if (!post.date) {
    console.warn(`  ! ${page.id} has no date and no created_time — skipped`);
    return null;
  }

  const children = stripExpiringImages(await listChildren(page.id));
  const blocks = await mapBlockList(children, getChildrenFiltered);

  const raw_title = rawTitleOf(page);
  const issueMatch = raw_title.match(/#\s*(\d+)/);

  return {
    section,
    issue_date: post.date,
    title: post.title,
    // The full bracket contents, exactly as Post.series holds them today, so
    // the rendered tag is unchanged. issue_number is a parsed convenience.
    series: post.series,
    raw_title,
    issue_number: issueMatch ? Number(issueMatch[1]) : null,
    summary: post.summary,
    blocks,
    plain_text: blocks.map(blockText).filter(Boolean).join("\n"),
    notion_page_id: page.id,
    notion_url: page.url ?? null,
    run_key: `notion:${page.id}`,
    // Staged. Flip to true only after --verify passes.
    published: false,
  };
}

// ---------------------------------------------------------------------------
// Supabase (PostgREST)
// ---------------------------------------------------------------------------

async function sb(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SUPABASE_SECRET_KEY!,
      authorization: `Bearer ${SUPABASE_SECRET_KEY}`,
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`supabase ${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return res;
}

async function existingPageIds(section: SectionKey): Promise<Set<string>> {
  const res = await sb(
    `newsletter?select=notion_page_id&section=eq.${section}&notion_page_id=not.is.null`
  );
  const rows: { notion_page_id: string }[] = await res.json();
  return new Set(rows.map((r) => r.notion_page_id));
}

async function upsert(rows: Row[]): Promise<any[]> {
  const res = await sb("newsletter?on_conflict=notion_page_id", {
    method: "POST",
    headers: { prefer: "resolution=merge-duplicates,return=representation" },
    body: JSON.stringify(rows),
  });
  return res.json();
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

async function runBackfill(): Promise<void> {
  console.log(COMMIT ? "Backfilling (writing)\n" : "Backfilling (dry run)\n");
  let total = 0;

  for (const section of sections) {
    const key = section.key;
    const pages = await listPages(section.notionId!);
    const seen = FORCE ? new Set<string>() : await existingPageIds(key);
    const todo = pages.filter((p) => !seen.has(p.id));

    console.log(
      `${key.padEnd(8)} ${String(pages.length).padStart(3)} pages in Notion, ` +
        `${seen.size} already in Supabase, ${todo.length} to write`
    );

    // Sequential: the per-page fanout already saturates MAX_CONCURRENT, and
    // ascending order has to be preserved for deterministic slug suffixes.
    const rows: Row[] = [];
    for (const page of todo) {
      const row = await buildRow(page, key);
      if (!row) continue;
      rows.push(row);
      if (rows.length % 25 === 0) console.log(`  … ${rows.length}/${todo.length}`);
    }

    if (!rows.length) {
      console.log("  nothing to do\n");
      continue;
    }

    if (COMMIT) {
      // One request per 25 rows: the slug trigger runs per row, and smaller
      // batches keep a mid-flight failure cheap to resume.
      for (let i = 0; i < rows.length; i += 25) {
        const written = await upsert(rows.slice(i, i + 25));
        for (const w of written) console.log(`  + ${w.section}/${w.slug}`);
      }
    } else {
      for (const r of rows.slice(0, 3)) {
        console.log(
          `  would write ${r.issue_date} "${r.title.slice(0, 60)}" ` +
            `(${r.blocks.length} blocks, series=${r.series ?? "none"})`
        );
      }
      if (rows.length > 3) console.log(`  … and ${rows.length - 3} more`);
    }

    total += rows.length;
    console.log("");
  }

  console.log(`${COMMIT ? "Wrote" : "Would write"} ${total} rows.`);
  if (droppedImages) {
    console.log(
      `Dropped ${droppedImages} Notion-hosted image blocks (expiring signed URLs).`
    );
  }
  if (!COMMIT) console.log("Re-run with --commit to write.");
}

/**
 * Postgres jsonb does not preserve object key order — it normalises it, so a
 * block written as {type, level, text} reads back as {text, type, level}. Array
 * order, which is the part that actually matters for blocks, is preserved.
 * Compare on a canonical key ordering so the diff reports real differences
 * rather than that normalisation.
 */
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        // Attached after the mapping by shared/audio.py, so a stored block
        // carries it and a freshly mapped one never will. Comparing it would
        // report every audio-bearing issue as a mapping divergence.
        .filter((k) => k !== "audio")
        .sort()
        .map((k) => [k, canonical((value as Record<string, unknown>)[k])])
    );
  }
  return value;
}

const sameBlocks = (a: unknown, b: unknown): boolean =>
  JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

async function runVerify(): Promise<void> {
  console.log("Verifying\n");
  let problems = 0;

  const counts = await (
    await sb("newsletter?select=section&limit=10000")
  ).json();
  const bySection = new Map<string, number>();
  for (const r of counts as { section: string }[]) {
    bySection.set(r.section, (bySection.get(r.section) ?? 0) + 1);
  }

  for (const section of sections) {
    const key = section.key;
    const notionCount = (await listPages(section.notionId!)).length;
    const rowCount = bySection.get(key) ?? 0;
    const ok = notionCount === rowCount;
    if (!ok) problems++;
    console.log(
      `${ok ? "ok  " : "FAIL"} ${key.padEnd(8)} notion=${notionCount} supabase=${rowCount}`
    );
  }

  const empty = await (
    await sb("newsletter?select=slug,section&blocks=eq.%5B%5D")
  ).json();
  if (empty.length) {
    problems++;
    console.log(`FAIL ${empty.length} rows have empty blocks`);
    for (const r of empty.slice(0, 10)) console.log(`       ${r.section}/${r.slug}`);
  } else {
    console.log("ok   no rows with empty blocks");
  }

  const rows: { slug: string; section: string }[] = await (
    await sb("newsletter?select=slug,section&limit=10000")
  ).json();
  const badSlugs = rows.filter((r) => !/^\d{4}-\d{2}-\d{2}-/.test(r.slug));
  if (badSlugs.length) {
    problems++;
    console.log(`FAIL ${badSlugs.length} slugs are not date-prefixed`);
    for (const r of badSlugs.slice(0, 10)) console.log(`       ${r.section}/${r.slug}`);
  } else {
    console.log("ok   every slug is date-prefixed");
  }

  // The real check: re-map every page from Notion and compare against what is
  // stored. This is the whole justification for writing the backfill in
  // TypeScript, so it is worth the second full pass.
  console.log("\nRe-mapping every page to compare blocks…");
  let compared = 0;
  let mismatched = 0;

  for (const section of sections) {
    const key = section.key;
    const stored: { notion_page_id: string; slug: string; blocks: Block[] }[] = await (
      await sb(`newsletter?select=notion_page_id,slug,blocks&section=eq.${key}&limit=10000`)
    ).json();
    const byId = new Map(stored.map((r) => [r.notion_page_id, r]));

    for (const page of await listPages(section.notionId!)) {
      const row = byId.get(page.id);
      if (!row) {
        problems++;
        mismatched++;
        console.log(`FAIL ${key}: notion page ${page.id} has no Supabase row`);
        continue;
      }
      const children = stripExpiringImages(await listChildren(page.id));
      const fresh = await mapBlockList(children, getChildrenFiltered);
      compared++;
      if (!sameBlocks(fresh, row.blocks)) {
        problems++;
        mismatched++;
        console.log(`FAIL blocks differ for ${key}/${row.slug} (${page.id})`);
      }
      if (compared % 50 === 0) console.log(`  … ${compared} compared`);
    }
  }

  console.log(
    `\n${compared} pages compared, ${mismatched} mismatched, ${problems} problems total.`
  );
  if (problems) process.exit(1);
  console.log("\nAll checks passed. Safe to run:");
  console.log("  update public.newsletter set published = true;");
}

// Not top-level await: package.json has no "type": "module", so the file may be
// transpiled to CJS depending on how it is invoked.
(VERIFY ? runVerify() : runBackfill()).catch((err) => {
  console.error(err);
  process.exit(1);
});
