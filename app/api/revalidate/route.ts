import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";
import { POST_TAG, POSTS_TAG, postTag } from "@/lib/notion";

// Issue bodies are cached with no expiry (lib/notion.ts), so this is the only
// thing that can pull a Notion edit through. Call it after changing an issue
// that's already published:
//
//   curl -X POST $SITE/api/revalidate -H "authorization: Bearer $REVALIDATE_SECRET"
//   curl -X POST $SITE/api/revalidate -H "authorization: Bearer $REVALIDATE_SECRET" \
//        -H 'content-type: application/json' -d '{"id":"<notion-page-id>"}'
//
// With an id it evicts that one issue; without, every body. Lists refresh
// either way — they're cheap.

export async function POST(request: Request) {
  const secret = process.env.REVALIDATE_SECRET;
  // With no secret configured there's no way to authenticate a caller, so the
  // route stays shut rather than becoming an open cache-buster.
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let id: string | null = null;
  try {
    const body = await request.json();
    if (typeof body?.id === "string" && body.id.trim()) id = body.id.trim();
  } catch {
    // No body, or not JSON. Means "refresh everything", which is the default.
  }

  // "max" marks the entries stale rather than dropping them, so the next reader
  // is served the old issue instantly while Notion is re-queried behind them.
  // Evicting outright would hand that reader the same ~4s wait this whole change
  // exists to remove.
  revalidateTag(POSTS_TAG, "max");
  revalidateTag(id ? postTag(id) : POST_TAG, "max");

  return NextResponse.json({ revalidated: id ?? "all" });
}
