import Link from "next/link";
import { formatShortDate } from "@/lib/feed";
import type { Post, Section } from "@/lib/types";

export default function SectionModule({
  section,
  posts,
}: {
  section: Section;
  posts: Post[];
}) {
  return (
    <section className="section-module" id={section.key}>
      <span className="label">
        {section.number} / {section.label}
      </span>
      <h2 className="section-module__title">
        <Link href={`/section/${section.key}`}>{section.title}</Link>
      </h2>
      <ul className="section-module__list">
        {posts.map((post) => (
          <li key={post.id}>
            <Link href={`/post/${post.section}/${post.id}`} prefetch={false}>
              <span className="section-module__item-title">{post.title}</span>
              <span className="section-module__date">
                {formatShortDate(post.date)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Link href={`/section/${section.key}`} className="arrow-link">
        View all <span aria-hidden>→</span>
      </Link>
    </section>
  );
}
