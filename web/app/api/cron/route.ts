import { NextResponse } from "next/server";
import { WORKFLOWS, gh, SCHEDULED_SUFFIX } from "@/lib/github";
import type { SectionKey } from "@/lib/types";

// Starts the daily issues. Vercel Cron calls this; GitHub's own `schedule:`
// trigger used to, and routinely fired two hours late — the 08:20 KST startup
// run started around 10:30, so a reader opening the site that morning found
// yesterday's issue on top.
//
// Each section has a primary cron at its slot and a later catch-up cron that
// names several sections at once. Both come through here and both ask the same
// question first: has this section's scheduled run for today (KST) already
// succeeded or started? If so there is nothing to do. That makes the catch-up
// a no-op on a normal day, retries a run that failed, and absorbs the duplicate
// deliveries Vercel Cron is allowed to make — a second edition-1 run would
// replace the morning's issue with a different one and burn an issue number.
//
// Vercel sends `Authorization: Bearer $CRON_SECRET` on every cron request.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

/** Midnight at the start of today in Seoul, as a UTC ISO string. */
function kstMidnight(): string {
  const kst = new Date(Date.now() + KST_OFFSET_MS);
  kst.setUTCHours(0, 0, 0, 0);
  return new Date(kst.getTime() - KST_OFFSET_MS).toISOString().replace(".000", "");
}

type Run = {
  event: string;
  status: string;
  conclusion: string | null;
  display_title: string;
};

/** Whether today's scheduled issue for this workflow is done or on its way. */
async function alreadyRan(file: string, token: string): Promise<boolean> {
  const since = encodeURIComponent(`>=${kstMidnight()}`);
  const res = await gh(`/actions/workflows/${file}/runs?created=${since}&per_page=50`, token);
  if (!res.ok) throw new Error(`GitHub runs for ${file}: ${res.status}`);
  const data = (await res.json()) as { workflow_runs?: Run[] };
  return (data.workflow_runs ?? []).some(
    (r) =>
      (r.event === "schedule" || r.display_title.endsWith(SCHEDULED_SUFFIX)) &&
      (r.status !== "completed" || r.conclusion === "success")
  );
}

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "No GITHUB_TOKEN on this deployment." }, { status: 501 });
  }

  const sections = (new URL(request.url).searchParams.get("sections") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter((s): s is SectionKey => s in WORKFLOWS);
  if (sections.length === 0) {
    return NextResponse.json({ error: "No known sections named." }, { status: 400 });
  }

  const results: Record<string, string> = {};
  for (const section of sections) {
    const file = WORKFLOWS[section];
    try {
      if (await alreadyRan(file, token)) {
        results[section] = "already ran today";
        continue;
      }
      const res = await gh(`/actions/workflows/${file}/dispatches`, token, {
        method: "POST",
        body: JSON.stringify({ ref: "main", inputs: { scheduled: "true" } }),
      });
      results[section] = res.ok
        ? "dispatched"
        : `GitHub refused (${res.status}): ${(await res.text()).slice(0, 200)}`;
    } catch (e) {
      results[section] = e instanceof Error ? e.message : "failed";
    }
  }

  // Logged so a missing issue can be traced from the Vercel logs alone.
  console.log("cron", JSON.stringify(results));
  const failed = Object.values(results).some(
    (r) => r !== "dispatched" && r !== "already ran today"
  );
  return NextResponse.json({ results }, { status: failed ? 502 : 200 });
}
