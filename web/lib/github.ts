import "server-only";
import type { SectionKey } from "@/lib/types";

// The generators are Python jobs in GitHub Actions; the site only ever asks
// GitHub to start one. Shared by /api/generate (extra issues on demand) and
// /api/cron (the daily schedule).

const REPO = process.env.GITHUB_REPO ?? "xparadigms/newsletter-hub";

export const WORKFLOWS: Record<SectionKey, string> = {
  startup: "startup-daily.yml",
  business: "business-daily.yml",
  fintech: "daily-newsletter.yml",
  japan: "japan-daily.yml",
  watch: "watch-weekly.yml",
  china: "china-daily.yml",
  mandarin: "mandarin-daily.yml",
  stocks: "stocks-daily.yml",
};

// Every workflow's run-name ends with this when the cron started it, which is
// the only way to tell those runs apart from site-requested extras: both are
// workflow_dispatch, and the runs API does not return a run's inputs.
export const SCHEDULED_SUFFIX = "(scheduled)";

export function gh(path: string, token: string, init?: RequestInit) {
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
