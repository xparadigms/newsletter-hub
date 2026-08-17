// Shared navigation state for the app-shell chrome. Kept in sessionStorage so
// it survives client-side navigation but never leaks between tabs/sessions.

const DEPTH_KEY = "nav-depth";

export function getDepth(): number {
  try {
    return Number(sessionStorage.getItem(DEPTH_KEY) ?? "0") || 0;
  } catch {
    return 0;
  }
}

export function setDepth(value: number) {
  try {
    sessionStorage.setItem(DEPTH_KEY, String(Math.max(0, value)));
  } catch {}
}

// Where "back" should land when there is no history to pop — i.e. the app was
// opened cold on this URL from a shared link or the Home Screen.
export function parentPath(pathname: string): string {
  const post = pathname.match(/^\/post\/([^/]+)\//);
  if (post) return `/section/${post[1]}`;
  if (pathname.startsWith("/section/")) return "/";
  return "/";
}
