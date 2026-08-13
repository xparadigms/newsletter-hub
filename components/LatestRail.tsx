import Link from "next/link";
import { getSection } from "@/lib/config";
import { formatShortDate } from "@/lib/feed";
import type { Post } from "@/lib/types";

export default function LatestRail({ posts }: { posts: Post[] }) {
  return (
    <aside className="latest" aria-label="Latest across all newsletters">
      <span className="label">Latest</span>
      <ul className="latest__list">
        {posts.map((post) => (
          <li key={post.id} className="latest__item">
            <Link href={`/post/${post.section}/${post.id}`} prefetch={false}>
              <span className="latest__meta label">
                {getSection(post.section)?.label} · {formatShortDate(post.date)}
              </span>
              <span className="latest__title">{post.title}</span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
