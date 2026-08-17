// Generates iOS launch images. Without apple-touch-startup-image, iOS shows a
// blank white screen while the app boots, which is the least native moment in
// the whole experience.
//
// Usage: node scripts/gen-splash.mjs
// Requires Google Chrome (same headless approach used for the app icons).

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// width x height in CSS px, and the device pixel ratio iOS reports.
export const DEVICES = [
  { w: 320, h: 568, r: 2 }, // SE 1st gen
  { w: 375, h: 667, r: 2 }, // SE 2/3, 8
  { w: 390, h: 844, r: 3 }, // 12/13/14, 16e
  { w: 393, h: 852, r: 3 }, // 14 Pro, 15, 16
  { w: 402, h: 874, r: 3 }, // 16 Pro
  { w: 414, h: 896, r: 2 }, // 11, XR
  { w: 428, h: 926, r: 3 }, // 12/13/14 Pro Max
  { w: 430, h: 932, r: 3 }, // 14 Pro Max, 15/16 Plus
  { w: 440, h: 956, r: 3 }, // 16 Pro Max
];

const THEMES = {
  light: { bg: "#ffffff", fg: "#000000", accent: "#10b981" },
  dark: { bg: "#0d0d0d", fg: "#f2f2f2", accent: "#10b981" },
};

const html = ({ w, h, bg, fg, accent }) => `<html><head>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&display=swap" rel="stylesheet">
<style>
 html,body{margin:0;padding:0}
 .s{width:${w}px;height:${h}px;background:${bg};display:flex;flex-direction:column;
    align-items:center;justify-content:center;font-family:'Archivo',-apple-system,sans-serif}
 .m{color:${fg};font-weight:700;font-size:${Math.round(w * 0.135)}px;letter-spacing:-.05em;line-height:1}
 .b{width:${Math.round(w * 0.19)}px;height:${Math.round(w * 0.018)}px;background:${accent};
    margin-top:${Math.round(w * 0.055)}px;border-radius:2px}
</style></head><body><div class="s"><div class="m">TB</div><div class="b"></div></div></body></html>`;

const outDir = new URL("../public/splash/", import.meta.url).pathname;
mkdirSync(outDir, { recursive: true });

const work = join(tmpdir(), `splash-${process.pid}`);
mkdirSync(work, { recursive: true });

for (const d of DEVICES) {
  for (const [theme, colors] of Object.entries(THEMES)) {
    const px = { w: d.w * d.r, h: d.h * d.r };
    const page = join(work, `${d.w}x${d.h}-${theme}.html`);
    writeFileSync(page, html({ w: px.w, h: px.h, ...colors }));
    const out = join(outDir, `splash-${d.w}x${d.h}-${theme}.png`);
    execFileSync(
      CHROME,
      [
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--virtual-time-budget=4000",
        `--window-size=${px.w},${px.h}`,
        `--screenshot=${out}`,
        `file://${page}`,
      ],
      { stdio: "ignore" }
    );
    console.log(`  ${out.split("/").pop()}  ${px.w}x${px.h}`);
  }
}

rmSync(work, { recursive: true, force: true });
console.log(`\nDone — ${DEVICES.length * 2} launch images in public/splash/`);
