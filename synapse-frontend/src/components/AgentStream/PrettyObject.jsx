import React from "react";

const K = ({ children }) => <span className="text-gray-400">{children}</span>;

// Helper to check for place-like objects (merchants, lockers, etc.)
const isPlaceObject = (obj) => {
  return typeof obj === "object" && obj !== null && (obj.name || obj.displayName?.text);
};

// Helper to strip out unwanted keys
const stripUnwantedKeys = (obj) => {
  if (!obj || typeof obj !== 'object') return obj;
  const newObj = { ...obj };
  const unwantedKeys = new Set([
    'session_id', 
    'fcm_token', 
    'token', 
    'access_token', 
    'id', 
    'place_id',
    // New keys to be removed as per your request
    'polyline',
    'embedUrl',
    'driver_token',
    'passenger_token',
    'customer_token',
  ]);
  for (const key of Object.keys(newObj)) {
    if (unwantedKeys.has(key)) {
      delete newObj[key];
    }
  }
  return newObj;
};

// Recursive function to render data with collapsible sections
function renderData(data, key = null) {
  if (data == null || (typeof data === 'object' && Object.keys(data).length === 0)) {
    return <div className="text-gray-400">—</div>;
  }
  if (typeof data !== "object") {
    return <span className="text-[var(--grab-text)] break-words">{String(data)}</span>;
  }

  // Handle arrays of place objects (e.g., lockers or merchants)
  if (Array.isArray(data) && data.every(isPlaceObject)) {
    return (
      <ul className="space-y-1">
        {data.map((item, i) => (
          <li key={item.id || i} className="rounded-lg bg-black/20 border border-[var(--grab-edge)] p-2">
            <details>
              <summary className="cursor-pointer font-medium text-[var(--grab-text)]">
                {item.name || item.displayName?.text || `Item ${i + 1}`}
              </summary>
              <div className="mt-2 pl-4">
                {renderData(stripUnwantedKeys(item))}
              </div>
            </details>
          </li>
        ))}
      </ul>
    );
  }

  // Handle other arrays of simple data
  if (Array.isArray(data)) {
    return data.length ? (
      <ul className="space-y-1">
        {data.map((item, i) => (
          <li key={i} className="rounded-lg bg-black/20 border border-[var(--grab-edge)] p-2">
            {renderData(item)}
          </li>
        ))}
      </ul>
    ) : (
      <div className="text-gray-400">[]</div>
    );
  }

  // Handle regular objects
  const entries = Object.entries(stripUnwantedKeys(data));
  if (!entries.length) {
    return <div className="text-gray-400">{`{}`}</div>;
  }
  
  return (
    <div className="mt-2 grid sm:grid-cols-1 gap-x-4 gap-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs uppercase tracking-wider text-[var(--grab-muted)]">{k}</dt>
          <dd className="rounded-lg bg-black/20 border border-[var(--grab-edge)] p-2 text-sm">
            {renderData(v, k)}
          </dd>
        </div>
      ))}
    </div>
  );
}

export default function PrettyObject({ data }) {
  // Check if data has a key named "lockers" and if its value is a list of places
  if (data?.lockers && Array.isArray(data.lockers) && data.lockers.every(isPlaceObject)) {
    return renderData(data.lockers);
  }
  
  return renderData(data);
}

export { K };