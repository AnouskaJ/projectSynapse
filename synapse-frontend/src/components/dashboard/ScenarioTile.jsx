import { Link } from "react-router-dom";

export default function ScenarioTile({ to, title, subtitle }){
  return (
    <Link
      to={to}
      className="surface-weak p-3 h-[96px] flex flex-col justify-between shadow-sm hover:border-[var(--grab-accent)] hover:shadow-md hover:-translate-y-[1px] transition"
    >
      <div className="flex items-center gap-2">
        <span className="text-base">🍔</span>
        <div className="font-semibold text-[var(--grab-accent)] text-[15px]">{title}</div>
      </div>
      <div className="text-xs opacity-70">{subtitle}</div>
      <div>
        <span className="inline-block btn-sm text-xs">Open</span>
      </div>
    </Link>
  );
}
