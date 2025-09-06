import KpiPill from "./KpiPill.jsx";

export default function KpiRow({ items = [] }) {
  return (
    <div className="kpi-row">
      {items.map((it, i) => (
        <KpiPill
          key={i}
          label={it.label}
          value={it.value}
          subtle={it.subtle}
          badge={it.badge}
        />
      ))}
    </div>
  );
}
