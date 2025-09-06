import React from 'react';

// Note: Ensure these paths correctly point to your existing map components.
// CORRECTED PATHS: Pointing to 'AgentStream' directory instead of 'agent'.
import AltRoutesMap from '../AgentStream/AltRoutesMap';
import MapBox from '../AgentStream/MapBox';

/**
 * A smart map component that inspects the incoming event data and chooses
 * the best map renderer for the job. It handles cases with no map data,
 * multiple alternative routes, and single routes or marker sets.
 */
export default function UnifiedMap({ event }) {
  // Extract map data from the most recent relevant event
  const mapData = event?.observation?.map || event?.data?.map || null;

  // Case 1: No map data available in the event stream yet.
  if (!mapData) {
    return (
      <div className="h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20 p-4 text-sm text-[var(--grab-muted)] flex items-center justify-center">
        Map will render once available.
      </div>
    );
  }

  // Case 2: Data for multiple alternative routes is present. Use the feature-rich AltRoutesMap.
  if (mapData.kind === "directions" && Array.isArray(mapData.routes) && mapData.routes.length > 0) {
    return <AltRoutesMap routes={mapData.routes} bounds={mapData.bounds} />;
  }

  // Case 3: Data for a single route or markers. Use the general-purpose MapBox.
  return <MapBox payload={mapData} />;
}

