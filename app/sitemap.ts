import type { MetadataRoute } from "next";
import { SECTIONS, SITE } from "@/lib/config";
import { getAllPosts } from "@/lib/notion";

export const revalidate = 3600;

// Built from the cached post lists only — no article fetches, so this costs
// nothing beyond what the front page already pays for.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const posts = await getAllPosts();

  const issues = SECTIONS.flatMap((section) =>
    posts[section.key].map((post) => ({
      url: `${SITE.url}/post/${post.section}/${post.id}`,
      lastModified: post.date ? new Date(`${post.date}T00:00:00`) : undefined,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    }))
  );

  return [
    {
      url: SITE.url,
      changeFrequency: "daily",
      priority: 1,
    },
    ...SECTIONS.map((section) => ({
      url: `${SITE.url}/section/${section.key}`,
      changeFrequency: "daily" as const,
      priority: 0.9,
    })),
    ...issues,
  ];
}
