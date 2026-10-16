import PageTransition from "@/components/PageTransition";
import ProfileView from "@/components/ProfileView";

export const metadata = { title: "Profile" };

export default function ProfilePage() {
  return (
    <PageTransition>
      <ProfileView />
    </PageTransition>
  );
}
