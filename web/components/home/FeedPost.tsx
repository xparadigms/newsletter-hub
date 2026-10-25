"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import BottomSheet from "@/components/BottomSheet";
import CoverImage, { CoverCredit } from "@/components/home/CoverImage";
import SectionAvatar from "@/components/home/SectionAvatar";
import SaveButton from "@/components/home/SaveButton";
import { clearStoryQueue, storyModeOn } from "@/components/home/stories";
import { SITE } from "@/lib/config";
import { toggleSaved, useLibrary, type ShelfPost } from "@/lib/library";

export interface FeedItem extends ShelfPost {
  summary: string | null;
  sectionTitle: string;
  sectionLabel: string;
  sectionNumber: string;
  longDate: string | null;
  shortDate: string;
}

function ShareIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinejoin="round">
      <path d="M21 3 3 10.5l7.2 2.6L21 3Zm0 0-7.6 18-3.2-7.9" />
    </svg>
  );
}

/** One issue in the Home feed, laid out like an Instagram post: header, a
 *  square "picture" carrying the headline, actions, caption. Double-tap the
 *  picture to save it. */
export default function FeedPost({ item }: { item: FeedItem }) {
  const router = useRouter();
  const { isRead, isSaved } = useLibrary();
  const [menu, setMenu] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [burst, setBurst] = useState(0);
  const lastTap = useRef(0);
  const single = useRef<number | undefined>(undefined);

  const article = `/post/${item.section}/${item.id}`;
  const story = `/story/${item.section}/${item.id}`;
  const url = `${SITE.url}${article}`;

  const openStory = () => {
    clearStoryQueue();
    router.push(story, { transitionTypes: ["nav-present"] });
  };
  const open = () => {
    if (storyModeOn()) openStory();
    else router.push(article, { transitionTypes: ["nav-forward"] });
  };
  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ title: item.title, url });
      else await navigator.clipboard.writeText(url);
    } catch {}
  };

  // A tap opens the issue; a second tap within 280ms makes it a double-tap,
  // which saves instead. Waiting out the window is what Instagram does too.
  const onPicture = () => {
    const now = Date.now();
    if (now - lastTap.current < 280) {
      window.clearTimeout(single.current);
      lastTap.current = 0;
      if (!isSaved(item)) toggleSaved(item);
      setBurst((n) => n + 1);
      navigator.vibrate?.(10);
      return;
    }
    lastTap.current = now;
    single.current = window.setTimeout(open, 280);
  };

  return (
    <article className="post">
      <header className="post__head">
        <button type="button" className="post__avatar" onClick={openStory} aria-label="Play as a story">
          <SectionAvatar section={item.section} size={32} unseen={!isRead(item)} />
        </button>
        <div className="post__who">
          <Link href={`/section/${item.section}`} className="post__name" transitionTypes={["nav-forward"]}>
            {item.sectionTitle}
          </Link>
          {item.series && <span className="post__series">{item.series}</span>}
        </div>
        <button type="button" className="icon-button" onClick={() => setMenu(true)} aria-label="More">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="currentColor">
            <circle cx="5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="19" cy="12" r="1.7" />
          </svg>
        </button>
      </header>

      <div
        className="post__picture"
        data-section={item.section}
        role="link"
        tabIndex={0}
        aria-label={`Read ${item.title}`}
        onClick={onPicture}
        onKeyDown={(e) => e.key === "Enter" && open()}
        data-cover={item.cover?.url ? "" : undefined}
      >
        <CoverImage cover={item.cover} className="post__photo" />
        <span className="label post__eyebrow">
          {item.sectionNumber} / {item.sectionLabel}
        </span>
        <h2 className="post__headline">{item.title}</h2>
        {item.longDate && <span className="label post__date">{item.longDate}</span>}
        {burst > 0 && (
          <span key={burst} className="post__burst" aria-hidden>
            <svg width="96" height="96" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 3.5h12a.5.5 0 0 1 .5.5v16.4a.3.3 0 0 1-.48.24L12 16.2l-6.02 4.44a.3.3 0 0 1-.48-.24V4a.5.5 0 0 1 .5-.5Z" />
            </svg>
          </span>
        )}
      </div>

      <div className="post__actions">
        <Link href={article} className="icon-button" transitionTypes={["nav-forward"]} aria-label="Read article">
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" />
          </svg>
        </Link>
        <button type="button" className="icon-button" onClick={openStory} aria-label="Play as a story">
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinejoin="round">
            <rect x="3.5" y="5" width="17" height="14" rx="3" /><path d="m10.5 9.5 4 2.5-4 2.5z" fill="currentColor" />
          </svg>
        </button>
        <button type="button" className="icon-button" onClick={share} aria-label="Share">
          <ShareIcon />
        </button>
        <span className="post__spacer" />
        <SaveButton post={item} />
      </div>

      <div className="post__caption">
        {item.summary && (
          <p className="post__summary" data-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
            <strong>{item.sectionLabel}</strong> {item.summary}
          </p>
        )}
        <span className="post__when">
          {item.shortDate}
          {item.cover?.url && (
            <>
              {" · "}
              <CoverCredit cover={item.cover} className="post__credit" />
            </>
          )}
        </span>
      </div>

      <BottomSheet open={menu} onClose={() => setMenu(false)} title={item.sectionTitle}>
        <ul className="action-list">
          <li><Link href={article} onClick={() => setMenu(false)} transitionTypes={["nav-forward"]}>Read article</Link></li>
          <li><button type="button" onClick={() => { setMenu(false); openStory(); }}>Play as a story</button></li>
          <li><Link href={`/section/${item.section}`} onClick={() => setMenu(false)} transitionTypes={["nav-forward"]}>Go to {item.sectionTitle}</Link></li>
          <li><button type="button" onClick={() => { setMenu(false); toggleSaved(item); }}>{isSaved(item) ? "Remove from Saved" : "Save"}</button></li>
          <li><button type="button" onClick={() => { setMenu(false); share(); }}>Share</button></li>
        </ul>
      </BottomSheet>
    </article>
  );
}
