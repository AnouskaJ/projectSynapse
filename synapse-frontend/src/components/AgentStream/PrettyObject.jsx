import React from "react";

const K = ({ children }) => <span className="text-gray-400">{children}</span>;

export default function PrettyObject({ data }) {
  if (data == null) return <div className="text-gray-400">—</div>;
  if (typeof data !== "object") return <div className="text-gray-200 break-words">{String(data)}</div>;

  /* Array */
  if (Array.isArray(data))
    return data.length ? (
      <ul className="space-y-1">
        {data.map((item, i) => (
          <li key={i} className="rounded-lg bg-black/20 border border-[var(--grab-edge)] p-2">
            <PrettyObject data={item} />
          </li>
        ))}
      </ul>
    ) : (
      <div className="text-gray-400">[]</div>
    );

  /* Object */
  const entries = Object.entries(data);
  if (!entries.length) return <div className="text-gray-400">{`{}`}</div>;

  return (
    <dl className="grid sm:grid-cols-2 gap-x-4 gap-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs uppercase tracking-wider text-gray-400">{k}</dt>
          <dd className="text-gray-200">
            <PrettyObject data={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export { K };
