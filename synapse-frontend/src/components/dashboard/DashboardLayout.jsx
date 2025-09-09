export default function DashboardLayout({ sidebar, children }) {
  return (
    <div className="min-h-screen grid grid-cols-1 gap-6 md:grid-cols-[300px_1fr]">
      {/* Left: sidebar column stays top-aligned */}
      <aside className="space-y-4 px-4 md:px-0">{sidebar}</aside>

      {/* Right: center the content both vertically & horizontally */}
      <section className="flex items-center justify-center px-4">
        {/* This wrapper gives a nice readable max width */}
        <div className="w-full max-w-4xl">{children}</div>
      </section>
    </div>
  );
}
