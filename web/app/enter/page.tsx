import EnterForm from "@/components/EnterForm";
import { SITE } from "@/lib/config";

export const metadata = { title: "Enter", robots: { index: false } };

export default async function EnterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const next = (await searchParams).next ?? "/";
  return (
    <main className="enter-page">
      <div className="container">
        <p className="label">{SITE.name}</p>
        <h1>{SITE.tagline}</h1>
        <EnterForm next={next} />
      </div>
    </main>
  );
}
