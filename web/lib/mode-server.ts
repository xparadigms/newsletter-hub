import "server-only";
import { cookies } from "next/headers";
import { DEFAULT_MODE, isMode, MODE_COOKIE, modeInfo, type ModeInfo } from "./mode";

/** The reader's mode, from the cookie ModeSwitch sets. Reading it makes the
 *  page render per request, which every page that calls this already does. */
export async function getMode(): Promise<ModeInfo> {
  const value = (await cookies()).get(MODE_COOKIE)?.value;
  return modeInfo(isMode(value) ? value : DEFAULT_MODE);
}
