import type { MetadataRoute } from "next";
import { SITE } from "@/lib/config";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Story mode is a second presentation of content that already exists at
      // /post/*; keeping it out avoids duplicate-content indexing.
      disallow: ["/story/", "/api/", "/offline"],
    },
    sitemap: `${SITE.url}/sitemap.xml`,
  };
}
