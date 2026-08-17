import { revalidatePath, revalidateTag } from "next/cache";
import { NextResponse } from "next/server";
import { POSTS_TAG } from "@/lib/posts";

// Pulls a corrected issue through ahead of the ISR window. The generators call
// it after a successful write, so a new issue appears immediately instead of
// within five minutes:
//
//   curl -X POST $SITE/api/revalidate -H "authorization: Bearer $REVALIDATE_SECRET"
//   curl -X POST $SITE/api/revalidate -H "authorization: Bearer $REVALIDATE_SECRET" \
//        -H 'content-type: application/json' -d '{"section":"china","slug":"..."}'
//
// With section+slug it refreshes that issue's pages; without, just the lists.

export async function POST(request: Request) {
  const secret = process.env.REVALIDATE_SECRET;
  // With no secret configured there's no way to authenticate a caller, so the
  // route stays shut rather than becoming an open cache-buster.
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let section: string | null = null;
  let slug: string | null = null;
  try {
    const body = await request.json();
    if (typeof body?.section === "string") section = body.section.trim() || null;
    if (typeof body?.slug === "string") slug = body.slug.trim() || null;
  } catch {
    // No body, or not JSON. Means "refresh the lists", which is the default.
  }

  // Lists are tagged and cheap to rebuild. "max" marks them stale rather than
  // dropping them, so the next reader gets the current list instantly while it
  // refreshes behind them.
  revalidateTag(POSTS_TAG, "max");

  // Bodies are not tagged. lib/posts.ts wraps getPost in React cache() only,
  // which lives for one render — reading a single indexed row does not need a
  // cross-request cache the way assembling ~45 Notion calls did. What actually
  // holds a stale issue is the route's own ISR entry, so the path is what has
  // to be invalidated. Tagging it instead would look right and do nothing.
  if (section && slug) {
    revalidatePath(`/post/${section}/${slug}`);
    revalidatePath(`/story/${section}/${slug}`);
  }

  return NextResponse.json({ revalidated: slug ? `${section}/${slug}` : "lists" });
}
