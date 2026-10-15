// Dumps how the site annotates and decks each issue in a samples file, for
// comparison with the iOS port (ios/Parity). Usage: npx tsx scripts/parity-dump.ts samples.json
import { readFileSync } from "node:fs";
import { getSection } from "../lib/config";
import { buildDeck } from "../lib/story";
import { annotateBlocks, readingTime } from "../lib/text";
import type { Block, PostDetail, SectionKey } from "../lib/types";

function numberParts(blocks: Block[]): Block[] {
  let n = 0;
  return blocks.map((b) =>
    b.type === "heading" && b.text.trimStart().startsWith("【") && !/^\d+\.\s/.test(b.text)
      ? { ...b, text: `${n++}. ${b.text.trimStart()}` }
      : b
  );
}

const rows = JSON.parse(readFileSync(process.argv[2], "utf8"));
for (const r of rows) {
  const section = getSection(r.section)!;
  const blocks: Block[] = r.section === "stocks" ? numberParts(r.blocks) : r.blocks;
  const post: PostDetail = { id: r.slug, section: r.section as SectionKey, title: r.title, series: r.series, date: r.issue_date, summary: r.summary, blocks };
  const a = annotateBlocks(blocks, { hanLang: section.sourceLang === "zh" ? "zh" : "ja" });
  const minutes = readingTime(a);
  console.log(`# ${r.section}/${r.slug} minutes=${minutes}`);
  for (const x of a) {
    const readings = x.ruby ? x.ruby.filter((s) => s.reading).length : -1;
    console.log(`A ${x.block.type} ${x.lang ?? "-"} ${x.kicker ? "K" : "."} ${readings}`);
  }
  const deck = buildDeck(a, post, section, minutes);
  for (const c of deck) {
    if (c.kind === "content") console.log(`C content ${c.blocks.length} ${c.blocks.map((b) => (b.lang ?? "-")).join("")} ${c.subtitle ? "S" : "."} ${c.kicker ? "K" : "."}`);
    else console.log(`C ${c.kind}`);
  }
}
