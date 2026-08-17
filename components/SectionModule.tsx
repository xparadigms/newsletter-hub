import Link from "next/link";
import PrefetchLink from "@/components/PrefetchLink";
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
        <Link href={`/section/${section.key}`} transitionTypes={["nav-forward"]}>
          {section.title}
        </Link>
      </h2>
      <ul className="section-module__list">
        {posts.map((post) => (
          <li key={post.id}>
            <PrefetchLink
              href={`/post/${post.section}/${post.id}`}
              transitionTypes={["nav-forward"]}
            >
              <span className="section-module__item-title">{post.title}</span>
              <span className="section-module__date">
                {formatShortDate(post.date)}
              </span>
            </PrefetchLink>
          </li>
        ))}
      </ul>
      <Link
        href={`/section/${section.key}`}
        className="arrow-link"
        transitionTypes={["nav-forward"]}
      >
        View all <span aria-hidden>→</span>
      </Link>
    </section>
  );
}
