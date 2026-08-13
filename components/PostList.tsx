import Link from "next/link";
import type { Post } from "@/lib/types";

function formatDate(date: string | null): string {
  if (!date) return "—";
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export default function PostList({ posts }: { posts: Post[] }) {
  if (posts.length === 0) {
    return <p className="section__desc">Nothing published here yet.</p>;
  }
  return (
    <ul className="post-list">
      {posts.map((post) => (
        <li key={post.id} className="post-row">
          <Link href={`/post/${post.section}/${post.id}`} prefetch={false}>
            <span className="post-row__date">{formatDate(post.date)}</span>
            <span>
              <span className="post-row__title">{post.title}</span>
              {post.series && (
                <span className="post-row__tags">
                  <span className="tag">{post.series}</span>
                </span>
              )}
            </span>
            <span className="post-row__arrow" aria-hidden>
              →
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
