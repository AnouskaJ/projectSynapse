export default function KpiPill({ label, value, subtle, badge }) {
  return (
    <div className="kpi-pill">
      <div className="label">{label}</div>
      <div className={`value ${subtle ? "opacity-70" : ""}`}>
        {badge ? <span className="badge">{value}</span> : value}
      </div>
    </div>
  );
}
