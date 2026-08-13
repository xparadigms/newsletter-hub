import { getPost } from "./notion";
import type { Post } from "./types";

// Opening an issue that isn't cached costs ~45 Notion calls and takes seconds.
// Warming fills getPost's data cache after a list page has already responded, so
// the reader's next tap is served from cache instead of from Notion.
//
// This is safe to call on every list render: getPost is wrapped in
// unstable_cache, so warming an already-warm issue is a cache hit costing zero
// Notion calls. Only genuinely cold issues do any work.

// A cold issue costs ~4s to assemble, and warming runs inside a 60s budget, so
// ten fits with headroom. Ten dailies is roughly a fortnight of back-issues.
const WARM_COUNT = 10;

export async function warmRecent(posts: Post[], count = WARM_COUNT) {
  // after() also runs while pages are prerendered, where warming is exactly
  // wrong: it makes the build do the expensive work this exists to avoid, four
  // sections at once, and pushed each section page past its build timeout.
  // Runtime only.
  if (process.env.NEXT_BUILD_PHASE) return;

  // Sequential on purpose. The parallel version of this is precisely what
  // overloaded Notion before, and there is no deadline out here — the response
  // has already been sent.
  for (const post of posts.slice(0, count)) {
    try {
      await getPost(post.id, post.section);
    } catch {
      // A cold issue that fails now simply stays cold; the reader's own request
      // will retry it. Never let warming surface as a request error.
    }
  }
}
