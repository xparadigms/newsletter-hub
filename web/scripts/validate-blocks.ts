/**
 * Validate a Block[] payload against the TypeScript union.
 *
 *   echo '<blocks json>' | npx tsx scripts/validate-blocks.ts
 *
 * Exits 0 when every block is valid, 1 listing the offenders otherwise.
 *
 * Run from web/. Used by shared/tests/test_china_blocks.py so the Python
 * generator's natively-built blocks are checked against the same union the
 * renderer switches on, rather than against a second description of it.
 */

import { findInvalidBlocks } from "../lib/blocks-guard";

async function main(): Promise<void> {
  const stdin = await new Promise<string>((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdin);
  } catch (err) {
    console.error(`not JSON: ${(err as Error).message}`);
    process.exit(1);
  }

  const problems = findInvalidBlocks(parsed);
  if (problems.length) {
    console.error(`${problems.length} invalid block(s):`);
    for (const p of problems) console.error(`  ${p}`);
    process.exit(1);
  }

  console.log(`ok: ${(parsed as unknown[]).length} blocks valid`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
