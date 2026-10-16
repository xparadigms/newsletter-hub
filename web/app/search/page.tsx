import PageTransition from "@/components/PageTransition";
import SearchPanel from "@/components/SearchPanel";

export const metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <PageTransition>
      <SearchPanel />
    </PageTransition>
  );
}
