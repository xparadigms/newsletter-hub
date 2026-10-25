// The reader's own shelf — issues saved, and issues read — kept in this
// browser's localStorage. The iOS app keeps the same two lists on the phone;
// nothing here is synced, by design: there are no accounts.
//
// Read through useLibrary(), which re-renders every subscriber when either list
// changes, in this tab or another.

import { useSyncExternalStore } from "react";
import type { Cover, Post, SectionKey } from "./types";

export interface ShelfPost {
  id: string;
  section: SectionKey;
  title: string;
  date: string | null;
  series: string | null;
  cover?: Cover | null;
}

interface Shelf {
  saved: ShelfPost[];
  read: ShelfPost[];
}

const SAVED_KEY = "shelf-saved";
const READ_KEY = "shelf-read";
// Rings and the Read grid only need the recent past.
const READ_LIMIT = 400;

const EMPTY: Shelf = { saved: [], read: [] };
let snapshot: Shelf | null = null;
const listeners = new Set<() => void>();

export const routeId = (p: { section: string; id: string }) => `${p.section}/${p.id}`;

function load(key: string): ShelfPost[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as ShelfPost[]) : [];
  } catch {
    return [];
  }
}

function current(): Shelf {
  if (!snapshot) snapshot = { saved: load(SAVED_KEY), read: load(READ_KEY) };
  return snapshot;
}

function write(next: Shelf) {
  snapshot = next;
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(next.saved));
    localStorage.setItem(READ_KEY, JSON.stringify(next.read));
  } catch {}
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Another tab changed the shelf.
  const onStorage = (e: StorageEvent) => {
    if (e.key === SAVED_KEY || e.key === READ_KEY) {
      snapshot = null;
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

const slim = (p: Post | ShelfPost): ShelfPost => ({
  id: p.id,
  section: p.section,
  title: p.title,
  date: p.date,
  series: p.series,
  cover: p.cover ?? null,
});

export function toggleSaved(post: Post | ShelfPost) {
  const shelf = current();
  const id = routeId(post);
  const saved = shelf.saved.some((p) => routeId(p) === id)
    ? shelf.saved.filter((p) => routeId(p) !== id)
    : [slim(post), ...shelf.saved];
  write({ ...shelf, saved });
}

export function markRead(post: Post | ShelfPost) {
  const shelf = current();
  const id = routeId(post);
  if (shelf.read[0] && routeId(shelf.read[0]) === id) return;
  const read = [slim(post), ...shelf.read.filter((p) => routeId(p) !== id)].slice(0, READ_LIMIT);
  write({ ...shelf, read });
}

/** The shelf, empty during server rendering and hydration. */
export function useLibrary() {
  const shelf = useSyncExternalStore(subscribe, current, () => EMPTY);
  return {
    saved: shelf.saved,
    read: shelf.read,
    isSaved: (p: { section: string; id: string }) => shelf.saved.some((s) => routeId(s) === routeId(p)),
    isRead: (p: { section: string; id: string }) => shelf.read.some((s) => routeId(s) === routeId(p)),
  };
}
