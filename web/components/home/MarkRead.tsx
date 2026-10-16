"use client";

import { useEffect } from "react";
import { markRead, type ShelfPost } from "@/lib/library";

/** Records an issue as read when its article or story is opened — what takes
 *  its section's ring off in the tray, and fills the Read grid. */
export default function MarkRead({ post }: { post: ShelfPost }) {
  useEffect(() => {
    markRead(post);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post.section, post.id]);
  return null;
}
