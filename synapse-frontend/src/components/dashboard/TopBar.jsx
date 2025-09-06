import { useAuth } from "../auth/AuthProvider.jsx";
import { humanAvatar } from "../../lib/avatar";

export default function TopBar() {
  const { user } = useAuth();
  const avatar = humanAvatar(user?.email || "guest");

  return (
    <div className="surface px-4 py-3 sticky top-[76px] z-[5] bg-[var(--grab-panel)]/70 backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold text-[var(--grab-accent)]">Enter Scenario Prompt</h1>
          <p className="text-sm text-[var(--grab-muted)]">Describe your scenario and choose a service to continue</p>
        </div>

        <div className="flex items-center gap-3">
          <button className="rounded-full border border-[var(--grab-edge)] px-4 py-2 text-sm hover:bg-white/5 transition">
            View &amp; Edit Prompt
          </button>
          <img
            src={avatar}
            alt="User"
            className="h-9 w-9 rounded-full border border-[var(--grab-edge)] object-cover"
          />
        </div>
      </div>
    </div>
  );
}
