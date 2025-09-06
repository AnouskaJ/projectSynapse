function Skel({ className = "" }) {
  return <div className={`h-3 w-full animate-pulse rounded bg-white/10 ${className}`} />;
}

export default function SummaryCard({ summary }) {
  return (
    <div className="gt-card summary-card p-3 mt-3">
      <div className="mb-2 text-sm font-semibold">Summary</div>
      {!summary ? (
        <div className="space-y-2">
          <Skel />
          <Skel />
          <Skel className="w-2/3" />
        </div>
      ) : (
        <pre className="summary-pre">{summary}</pre>
      )}
    </div>
  );
}
