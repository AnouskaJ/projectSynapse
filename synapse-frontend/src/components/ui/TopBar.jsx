export default function TopBar({ title = "projectSynapse", onOpenPrompt }) {
  return (
    <header className="gt-topbar">
      <div className="gt-topbar-title">{title}</div>
      <div className="gt-topbar-tools">
        <div className="gt-search">
          <svg width="16" height="16" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="m21 21l-4.3-4.3m1.3-4.7A7 7 0 1 1 4 12a7 7 0 0 1 14 0"
            />
          </svg>
          <input placeholder="Search rides, drivers..." />
        </div>

        <button className="btn btn-primary" onClick={onOpenPrompt}>
          View &amp; Edit Prompt
        </button>

        <button className="gt-icon" aria-label="Notifications">
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M12 22a2 2 0 0 0 2-2H10a2 2 0 0 0 2 2m6-6v-5a6 6 0 1 0-12 0v5l-2 2v1h16v-1z"
            />
          </svg>
        </button>
      </div>
    </header>
  );
}
