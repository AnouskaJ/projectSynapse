import { useAuth } from "../auth/AuthProvider.jsx";

function Card({ title, children }) {
  return (
    <div className="surface-sidebar rounded-xl p-4">
      {title && (
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--grab-muted)]">
          {title}
        </div>
      )}
      {children}
    </div>
  );
}

function HistoryItem({ title, time, excerpt }) {
  return (
    <button className="w-full text-left rounded-lg border border-transparent px-3 py-2 text-sm hover:border-[var(--grab-accent)] hover:bg-[var(--grab-panel)]/90 transition">
      <div className="flex items-center justify-between text-xs text-[var(--grab-muted)]">
        <span>{time}</span>
        <span>Today</span>
      </div>
      <div className="mt-1 font-medium">{title}</div>
      <div className="mt-1 line-clamp-2 text-xs opacity-70">{excerpt}</div>
    </button>
  );
}

export default function Sidebar() {
  const { user, logout } = useAuth();

  // fetch dynamic avatar (realistic human face)
  const avatarUrl =
    "https://randomuser.me/api/portraits/men/32.jpg"; // swap with women/N depending on user if desired

  return (
    <aside className="sidebar flex flex-col gap-4 p-4">
      {/* Profile Section */}
      <Card title="Signed in">
        <div className="flex items-center gap-3">
          <img
            src={avatarUrl}
            alt="Profile"
            className="h-10 w-10 rounded-full border border-[var(--grab-edge)] object-cover"
          />
          <div className="text-sm">
            <div className="font-semibold">
              {user?.email?.split("@")[0] || "Guest"}
            </div>
            <div className="text-xs text-[var(--grab-muted)]">Ops • Grab</div>
          </div>
        </div>
        <button
          onClick={logout}
          className="mt-3 w-full rounded-lg border border-[var(--grab-edge)] px-3 py-2 text-xs hover:border-[var(--grab-accent)] hover:bg-white/5 transition"
        >
          Sign out
        </button>
      </Card>

      {/* Quick actions */}
      <Card title="Quick Actions">
        <div className="grid grid-cols-2 gap-2">
          <button className="rounded-lg border border-[var(--grab-edge)] px-2 py-2 text-xs hover:border-[var(--grab-accent)] hover:bg-white/5 transition">
            + New
          </button>
          <button className="rounded-lg border border-[var(--grab-edge)] px-2 py-2 text-xs hover:border-[var(--grab-accent)] hover:bg-white/5 transition">
            Recent
          </button>
        </div>
      </Card>

      {/* Search logs */}
      <Card title="Search Logs">
        <input
          className="w-full rounded-lg border border-[var(--grab-edge)] bg-transparent px-3 py-2 text-xs outline-none focus:border-[var(--grab-accent)] transition"
          placeholder="Search by order or restaurant"
        />
      </Card>

      {/* Previous prompts */}
      <Card title="Previous Prompts">
        <div className="space-y-2">
          <HistoryItem
            title="GrabCar • Peak hour re-route"
            time="09:15"
            excerpt="Heavy rain near Orchard. Recommend pickup re-route and notify rider…"
          />
          <HistoryItem
            title="GrabFood • Unavailable customer"
            time="21:42"
            excerpt="Customer not answering at condo gate. Suggest guardhouse drop-off…"
          />
        </div>
      </Card>
    </aside>
  );
}
