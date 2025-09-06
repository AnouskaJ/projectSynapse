export default function DashboardLayout({ sidebar, children }) {
  // 300px sidebar + 24px gap + fluid main column
  return (
    <div className="min-h-[calc(100vh-140px)] grid grid-cols-1 gap-6 md:grid-cols-[300px_1fr]">
      <aside className="space-y-4">{sidebar}</aside>
      <section className="space-y-6">{children}</section>
    </div>
  );
}
