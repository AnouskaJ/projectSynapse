import DashboardLayout from "../components/dashboard/DashboardLayout.jsx";
import Sidebar from "../components/dashboard/Sidebar.jsx";
import PromptCard from "../components/dashboard/PromptCard.jsx";
import ScenarioTile from "../components/dashboard/ScenarioTile.jsx";

export default function Home(){
  return (
    <div className="space-y-6">
      <div className="hr-soft" />

      <DashboardLayout sidebar={<Sidebar />}>
        <PromptCard />

        <div className="hr-soft" />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <ScenarioTile to="/service/grabfood"    title="GrabFood"    subtitle="Food delivery scenarios" />
          <ScenarioTile to="/service/grabmart"    title="GrabMart"    subtitle="Mart / inventory scenarios" />
          <ScenarioTile to="/service/grabexpress" title="GrabExpress" subtitle="Parcel dispatch scenarios" />
          <ScenarioTile to="/service/grabcar"     title="GrabCar"     subtitle="Ride / traffic scenarios" />
        </div>
      </DashboardLayout>

      <div className="hr-soft" />
    </div>
  );
}
