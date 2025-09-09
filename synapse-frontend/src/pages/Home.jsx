import DashboardLayout from "../components/dashboard/DashboardLayout.jsx";
import Sidebar from "../components/dashboard/Sidebar.jsx";
import PromptCard from "../components/dashboard/PromptCard.jsx";

export default function Home() {
  return (
    // The layout now handles vertical centering; no extra wrappers needed
    <DashboardLayout sidebar={<Sidebar />}>
      <PromptCard />
    </DashboardLayout>
  );
}
