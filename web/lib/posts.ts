import "server-only";

import { createClient } from "@supabase/supabase-js";
import { unstable_cache } from "next/cache";
import { sectionKeys } from "./config";
import { cache } from "react";
import type { Block, Cover, Post, PostDetail, SectionKey } from "./types";

// Data layer over the Supabase `newsletter` table, which the four generators
// write before mirroring each issue to Notion and Google Calendar.
//
// The exported surface deliberately matches the Notion data layer this replaces,
// so lib/types.ts is unchanged and lib/text.ts, lib/story.ts, lib/feed.ts and
// every component compile untouched.
//
// "server-only" makes importing this from a client component a build error. The
// key below is the publishable one and is only good for reading published rows
// under RLS, but nothing here should ever reach the browser.

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_PUBLISHABLE_KEY;

export const dataConnected = Boolean(url && key);

const supabase =
  url && key ? createClient(url, key, { auth: { persistSession: false } }) : null;

// The list cache tag, invalidated on demand by /api/revalidate. There is no
// body tag: getPost is wrapped in React cache() only, so a body tag would have
// nothing attached to it — the route's ISR entry is what holds a stale issue,
// and /api/revalidate calls revalidatePath for that.
export const POSTS_TAG = "posts";

// Everything a list needs. Never "*": blocks is ~40KB a row and a section index
// is ~130 rows, so selecting it here would move megabytes per render for data
// no list ever displays.
const LIST_COLUMNS = "slug,section,title,series,issue_date,summary,cover";

interface Row {
  slug: string;
  section: SectionKey;
  title: string;
  series: string | null;
  issue_date: string | null;
  summary: string | null;
  cover: Cover | null;
}

function toPost(row: Row): Post {
  // id carries the slug: every href in the app is `/post/${section}/${id}`, so
  // routing follows from this one assignment.
  return {
    id: row.slug,
    section: row.section,
    title: row.title,
    series: row.series,
    date: row.issue_date,
    summary: row.summary,
    cover: row.cover ?? null,
  };
}

// Every list expires on the same 300s clock, so a regeneration is a burst of
// seven-plus concurrent queries. Supabase's gateway answered some of those
// with 504 Gateway Timeout, and the old code turned that into an empty list —
// which unstable_cache then held for the next five minutes. Three sections
// were blank for days while the query itself worked fine from anywhere else.
const ATTEMPTS = 3;
const BACKOFF_MS = 400;

async function fetchPosts(section: SectionKey): Promise<Post[]> {
  if (!supabase) return [];

  let lastError = "";
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const { data, error } = await supabase
      .from("newsletter")
      .select(LIST_COLUMNS)
      .eq("section", section)
      .order("issue_date", { ascending: false })
      .order("published_at", { ascending: false })
      .limit(500);

    if (!error) return (data as Row[]).map(toPost);

    lastError = error.message;
    console.error(
      `Failed to load posts for ${section} (attempt ${attempt}/${ATTEMPTS}):`,
      lastError
    );
    if (attempt < ATTEMPTS) {
      // Jittered so seven retries do not re-form the burst that caused this.
      await new Promise((r) =>
        setTimeout(r, BACKOFF_MS * attempt + Math.random() * 200)
      );
    }
  }

  // Throw, do not return []. A thrown revalidation leaves unstable_cache's
  // last good value in place, so a section stays populated through a bad
  // moment instead of going blank. Only a cold cache with no good value ever
  // sees this as an error, and that is the honest outcome.
  throw new Error(`posts for ${section} unavailable: ${lastError}`);
}

// Shared across home, section, article and search routes so one revalidation
// window costs one query per section rather than one per page.
export const getPosts = unstable_cache(fetchPosts, ["posts", "v4"], {
  revalidate: 300,
  tags: [POSTS_TAG],
});

export async function getAllPosts(): Promise<Record<SectionKey, Post[]>> {
  // Derived from SECTIONS rather than destructured, so adding a section is one
  // edit and forgetting one here is impossible. The cast is sound because the
  // Covers guard in lib/config.ts proves SECTIONS spans the union.
  const keys = sectionKeys();
  const lists = await Promise.all(keys.map((key) => getPosts(key)));
  return Object.fromEntries(
    keys.map((key, i) => [key, lists[i]])
  ) as Record<SectionKey, Post[]>;
}

export interface SectionHistory {
  section: SectionKey;
  /** The first issue's date. */
  first: string;
  /** Every published issue — lists stop at 500, so this is counted. */
  count: number;
}

async function fetchTimeline(): Promise<SectionHistory[]> {
  if (!supabase) return [];
  const rows = await Promise.all(
    sectionKeys().map(async (key) => {
      const { data, count, error } = await supabase
        .from("newsletter")
        .select("issue_date", { count: "exact" })
        .eq("section", key)
        .order("issue_date", { ascending: true })
        .order("published_at", { ascending: true })
        .limit(1);
      if (error) throw new Error(`timeline for ${key}: ${error.message}`);
      const first = (data?.[0] as { issue_date?: string } | undefined)?.issue_date;
      return first ? { section: key, first, count: count ?? 0 } : null;
    })
  );
  return rows
    .filter((r): r is SectionHistory => r !== null)
    .sort((a, b) => a.first.localeCompare(b.first));
}

/** When each newsletter began, for the timeline on The Brief's profile. */
export const getTimeline = unstable_cache(fetchTimeline, ["timeline", "v1"], {
  revalidate: 3600,
  tags: [POSTS_TAG],
});

// One indexed row, so no cross-request cache: the Notion version needed
// `revalidate: false` because assembling an issue cost ~45 API calls and ~4
// seconds. The route-level ISR cache is enough now, and React cache() still
// dedupes generateMetadata and the page component within a render.
export const getPost = cache(
  async (slug: string, section: SectionKey): Promise<PostDetail | null> => {
    if (!supabase) return null;
    const { data, error } = await supabase
      .from("newsletter")
      .select(`${LIST_COLUMNS},blocks`)
      .eq("section", section)
      .eq("slug", slug)
      .maybeSingle();

    if (error) {
      // A genuine "no row" arrives as data === null, not as an error, so
      // anything here is a transport or policy failure and must not be
      // rendered as a missing issue.
      console.error(`Failed to load ${section}/${slug}:`, error.message);
      throw new Error(error.message);
    }
    if (!data) return null;

    const row = data as Row & { blocks: Block[] };
    const blocks = row.blocks ?? [];
    return {
      ...toPost(row),
      blocks: section === "stocks" ? numberParts(blocks) : blocks,
    };
  }
);

/** Three Companies' parts, numbered from 0: "0. 【基本情報】(기본 정보)",
 *  "1. 【直近30日の動き】…". Done here rather than in the generator so every
 *  article already published is numbered too, and so the article page, story
 *  mode and the table of contents all read the same text. A leading "N. " is
 *  what headingContent renders as a heading number. */
function numberParts(blocks: Block[]): Block[] {
  let n = 0;
  return blocks.map((b) =>
    b.type === "heading" && b.text.trimStart().startsWith("【") && !/^\d+\.\s/.test(b.text)
      ? { ...b, text: `${n++}. ${b.text.trimStart()}` }
      : b
  );
}
