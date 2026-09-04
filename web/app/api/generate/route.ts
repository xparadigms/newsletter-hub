import { NextResponse } from "next/server";
import { SECTIONS } from "@/lib/config";
import type { SectionKey } from "@/lib/types";

// Ask GitHub to run a newsletter generator now, producing an EXTRA issue for
// today rather than replacing the scheduled one.
//
// The site cannot generate anything itself — the generators are Python jobs in
// GitHub Actions — so this route is a gate in front of workflow_dispatch. That
// makes the gate the whole security story, and it is deliberately two things:
//
//   1. A password, checked here on the server. It never reaches the browser.
//   2. A hard daily cap, because a password of this strength will not survive
//      contact with the internet forever and every run spends Anthropic
//      credits. The cap counts dispatches, not issues, so failed runs still
//      consume their share — that is the point: it caps spend, not output.
//
// The token needs `actions: write` on this repository and nothing else.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REPO = process.env.GITHUB_REPO ?? "xparadigms/newsletter-hub";
const MAX_PER_DAY = Number(process.env.GENERATE_MAX_PER_DAY ?? 4);

const WORKFLOWS: Record<SectionKey, string> = {
  startup: "startup-daily.yml",
  business: "business-daily.yml",
  fintech: "daily-newsletter.yml",
  japan: "japan-daily.yml",
  watch: "watch-weekly.yml",
  china: "china-daily.yml",
  mandarin: "mandarin-daily.yml",
};

function gh(path: string, token: string, init?: RequestInit) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
}

/** Dispatches started today, across every newsletter workflow. */
async function usedToday(token: string): Promise<number> {
  const since = new Date().toISOString().slice(0, 10);
  const res = await gh(
    `/actions/runs?event=workflow_dispatch&created=%3E%3D${since}&per_page=100`,
    token
  );
  if (!res.ok) throw new Error(`GitHub runs: ${res.status}`);
  const data = (await res.json()) as { workflow_runs?: { path?: string }[] };
  const files = new Set(Object.values(WORKFLOWS));
  return (data.workflow_runs ?? []).filter((r) =>
    files.has((r.path ?? "").replace(".github/workflows/", ""))
  ).length;
}

export async function POST(request: Request) {
  const password = process.env.GENERATE_PASSWORD;
  const token = process.env.GITHUB_TOKEN;
  if (!password || !token) {
    return NextResponse.json(
      { error: "Generation is not configured on this deployment." },
      { status: 501 }
    );
  }

  let body: { section?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Bad request." }, { status: 400 });
  }

  if (body.password !== password) {
    return NextResponse.json({ error: "Wrong password." }, { status: 401 });
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
