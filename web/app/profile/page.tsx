import PageTransition from "@/components/PageTransition";
import ProfileView, { type TimelineEntry } from "@/components/ProfileView";
import { getSection } from "@/lib/config";
import { getAllPosts, getTimeline } from "@/lib/posts";

export const revalidate = 3600;
export const metadata = { title: "Profile" };

function longDate(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

export default async function ProfilePage() {
  const [history, posts] = await Promise.all([getTimeline(), getAllPosts()]);
  const timeline: TimelineEntry[] = history.map((h) => {
    const last = posts[h.section][0]?.date;
    return {
      section: h.section,
      first: longDate(h.first),
      count: h.count,
      pausedSince: getSection(h.section)?.hideInNav && last ? longDate(last) : null,
    };
  });
  return (
    <PageTransition>
      <ProfileView timeline={timeline} />
    </PageTransition>
  );
}
