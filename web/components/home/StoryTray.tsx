"use client";

import { useRouter } from "next/navigation";
import SectionAvatar from "@/components/home/SectionAvatar";
import { setStoryQueue } from "@/components/home/stories";
import { useLibrary } from "@/lib/library";
import type { SectionKey } from "@/lib/types";

export interface TrayEntry {
  section: SectionKey;
  label: string;
  /** The section's newest issue. */
  id: string;
}

/** One story per section — its newest issue — with unread sections first. */
export default function StoryTray({ entries }: { entries: TrayEntry[] }) {
  const router = useRouter();
  const { isRead } = useLibrary();
  const unseen = (e: TrayEntry) => !isRead({ section: e.section, id: e.id });
  const ordered = [...entries.filter(unseen), ...entries.filter((e) => !unseen(e))];
  const href = (e: TrayEntry) => `/story/${e.section}/${e.id}`;

  return (
    <nav className="tray" aria-label="Stories">
      <ul className="tray__list">
        {ordered.map((e) => (
          <li key={e.section}>
            <a
              href={href(e)}
              className="tray__item"
              onClick={(ev) => {
                if (ev.metaKey || ev.ctrlKey) return;
                ev.preventDefault();
                setStoryQueue(ordered.map(href));
                router.push(href(e), { transitionTypes: ["nav-present"] });
              }}
            >
              <SectionAvatar section={e.section} size={64} unseen={unseen(e)} />
              <span className="tray__label">{e.label}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
