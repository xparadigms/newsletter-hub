import { NextResponse } from "next/server";
import { SECTIONS } from "@/lib/config";
import { getAllPosts } from "@/lib/notion";

export const revalidate = 300;

// List data only — no article fetches — so this costs nothing beyond what the
// front page already pays. Roughly 25KB for the whole archive, small enough to
// filter on the client.
export async function GET() {
  const posts = await getAllPosts();
  const index = SECTIONS.flatMap((section) =>
    posts[section.key].map((post) => ({
      i: post.id,
      s: post.section,
      t: post.title,
      d: post.date,
      r: post.series,
    }))
  );
  return NextResponse.json(index, {
    headers: { "Cache-Control": "public, max-age=300, stale-while-revalidate=3600" },
  });
}
