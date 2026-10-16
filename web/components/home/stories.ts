// Stories opened from the tray play on through the other sections, as
// Instagram moves from one account to the next. The order is kept for the
// length of the visit; StoryViewer reads it when it runs off either end.

const KEY = "story-queue";

const RETURN = "story-return";

/** Remembers the page a story is opened from, so closing it goes back there.
 *  An article is never a return point: a story is put away to a list. */
function rememberReturn() {
  try {
    const path = location.pathname;
    if (!path.startsWith("/story/") && !path.startsWith("/post/")) sessionStorage.setItem(RETURN, path);
  } catch {}
}

export function storyReturn(): string | null {
  try {
    return sessionStorage.getItem(RETURN);
  } catch {
    return null;
  }
}

export function setStoryQueue(hrefs: string[]) {
  rememberReturn();
  try {
    sessionStorage.setItem(KEY, JSON.stringify(hrefs));
  } catch {}
}

export function clearStoryQueue() {
  rememberReturn();
  try {
    sessionStorage.removeItem(KEY);
  } catch {}
}

/** The issue before or after `href` in the tray's order, if it is in it. */
export function queueNeighbour(href: string, step: 1 | -1): string | null | undefined {
  try {
    const queue = JSON.parse(sessionStorage.getItem(KEY) ?? "[]") as string[];
    const i = queue.indexOf(href);
    if (i === -1) return undefined; // not playing from the tray
    return queue[i + step] ?? null;
  } catch {
    return undefined;
  }
}

/** Whether issues open as stories rather than articles (the story toggle). */
export function storyModeOn(): boolean {
  return document.documentElement.getAttribute("data-story") === "on";
}
