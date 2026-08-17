// Generates the Open Graph share card. Same headless-Chrome approach as the
// icons and splash screens.
//
// A static card rather than a per-issue rendered one: titles are frequently
// Japanese or Korean, and next/og would need a bundled CJK font to avoid
// rendering them as tofu. The real per-issue information travels in og:title
// and og:description, which every platform displays next to the image.
//
// Usage: node scripts/gen-og.mjs

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const html = `<html><head>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@450;600;700&display=swap" rel="stylesheet">
<style>
 html,body{margin:0;padding:0}
 .c{width:1200px;height:630px;background:#0d0d0d;color:#fff;
    font-family:'Archivo',-apple-system,sans-serif;
    display:flex;flex-direction:column;justify-content:space-between;
    padding:72px 80px;box-sizing:border-box}
 .top{display:flex;align-items:baseline;gap:16px}
 .mark{font-size:64px;font-weight:700;letter-spacing:-.04em}
 .by{font-size:24px;color:#8f8f8f}
 .head{font-size:56px;font-weight:700;letter-spacing:-.03em;line-height:1.12;max-width:940px}
 .bar{width:150px;height:12px;background:#10b981;border-radius:2px;margin-top:26px}
 .foot{display:flex;gap:28px;font-family:monospace;font-size:22px;
       letter-spacing:.08em;text-transform:uppercase;color:#8f8f8f}
</style></head><body><div class="c">
 <div class="top"><span class="mark">The Brief</span><span class="by">by Heechang</span></div>
 <div><div class="head">Daily briefs on startups, financial infrastructure, Japan and watches.</div>
 <div class="bar"></div></div>
 <div class="foot"><span>Startup</span><span>Fintech</span><span>Japan</span><span>Watch</span></div>
</div></body></html>`;

const work = join(tmpdir(), `og-${process.pid}`);
mkdirSync(work, { recursive: true });
const page = join(work, "og.html");
writeFileSync(page, html);

mkdirSync(new URL("../public/", import.meta.url).pathname, { recursive: true });
const out = new URL("../public/og.png", import.meta.url).pathname;

execFileSync(
  CHROME,
  [
    "--headless",
    "--disable-gpu",
    "--hide-scrollbars",
    "--virtual-time-budget=5000",
    "--window-size=1200,630",
    `--screenshot=${out}`,
    `file://${page}`,
  ],
  { stdio: "ignore" }
);

rmSync(work, { recursive: true, force: true });
console.log("Wrote public/og.png (1200x630)");
