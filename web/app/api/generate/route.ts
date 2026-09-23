import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SECTIONS } from "@/lib/config";
import { AUTH_COOKIE } from "@/middleware";
import { WORKFLOWS, gh, SCHEDULED_SUFFIX } from "@/lib/github";
import type { SectionKey } from "@/lib/types";

// Ask GitHub to run a newsletter generator now, producing an EXTRA issue for
// today rather than replacing the scheduled one.
//
// The site cannot generate anything itself — the generators are Python jobs in
// GitHub Actions — so this route is a gate in front of workflow_dispatch. That
// makes the gate the whole security story, and it is deliberately two things:
//
//   1. The site password, already presented at the door and carried in an
//      httpOnly cookie. Middleware would reject an anonymous request before it
//      reached this file; the check here is repeated rather than assumed,
//      because a route that depends on middleware staying configured is one
//      config edit away from being open.
//   2. A hard daily cap, because a password of this strength will not survive
//      contact with the internet forever and every run spends Anthropic
//      credits. The cap counts dispatches, not issues, so failed runs still
//      consume their share — that is the point: it caps spend, not output.
//
// The token needs `actions: write` on this repository and nothing else.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_PER_DAY = Number(process.env.GENERATE_MAX_PER_DAY ?? 4);

/** Extra issues requested today, across every newsletter workflow. */
async function usedToday(token: string): Promise<number> {
  const since = new Date().toISOString().slice(0, 10);
  const res = await gh(
    `/actions/runs?event=workflow_dispatch&created=%3E%3D${since}&per_page=100`,
    token
  );
  if (!res.ok) throw new Error(`GitHub runs: ${res.status}`);
  const data = (await res.json()) as {
    workflow_runs?: { path?: string; display_title?: string }[];
  };
  const files = new Set(Object.values(WORKFLOWS));
  // The daily cron dispatches too; those runs are the schedule, not extras.
  return (data.workflow_runs ?? []).filter(
    (r) =>
      files.has((r.path ?? "").replace(".github/workflows/", "")) &&
      !(r.display_title ?? "").endsWith(SCHEDULED_SUFFIX)
  ).length;
}

export async function POST(request: Request) {
  const password = process.env.SITE_PASSWORD ?? process.env.GENERATE_PASSWORD;
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json(
      { error: "No GitHub token on this deployment, so nothing can be dispatched." },
      { status: 501 }
    );
  }

  const jar = await cookies();
  if (password && jar.get(AUTH_COOKIE)?.value !== password) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  let body: { section?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Bad request." }, { status: 400 });
  }

  const section = body.section as SectionKey;
  if (!SECTIONS.some((s) => s.key === section)) {
    return NextResponse.json({ error: "Unknown newsletter." }, { status: 400 });
  }

  try {
    const used = await usedToday(token);
    if (used >= MAX_PER_DAY) {
      return NextResponse.json(
        {
          error: `Daily limit reached — ${used} of ${MAX_PER_DAY} generations used today.`,
        },
        { status: 429 }
      );
    }

    // Edition 2 is the first extra of the day. Anything already at 2 keeps
    // counting up, so a second extra does not overwrite the first: the run_key
    // carries the edition.
    const res = await gh(`/actions/workflows/${WORKFLOWS[section]}/dispatches`, token, {
      method: "POST",
      body: JSON.stringify({
        ref: "main",
        inputs: { edition: String(2 + used) },
      }),
    });
    if (!res.ok) {
      const detail = await res.text();
      return NextResponse.json(
        { error: `GitHub refused the run (${res.status}).`, detail: detail.slice(0, 300) },
        { status: 502 }
      );
    }

    return NextResponse.json({
      ok: true,
      remaining: MAX_PER_DAY - used - 1,
      // The run takes several minutes and this route does not wait for it.
      message: "Generating. The new issue appears in a few minutes.",
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Dispatch failed." },
      { status: 502 }
    );
  }
}
