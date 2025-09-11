import React from 'react';

import AltRoutesMap from '../AgentStream/AltRoutesMap';
import MapBox from '../AgentStream/MapBox';
import MerchantMap from '../AgentStream/MerchantMap.jsx';

/**
 * A smart map component that inspects the incoming event data and chooses
 * the best map renderer for the job. It handles cases with no map data,
 * multiple alternative routes, and single routes or marker sets.
 */
export default function UnifiedMap({ event }) {
  // Extract map data from all potential sources within the event object
  const mapData = event?.observation?.map || event?.data?.map || null;
  const merchants = event?.observation?.merchants || event?.data?.merchants;
  const lockers = event?.observation?.lockers || event?.data?.lockers;
  const locations = merchants || lockers;

  // Case 1: Data for multiple alternative routes is present.
  if (mapData?.kind === "directions" && Array.isArray(mapData.routes) && mapData.routes.length > 0) {
    return (
      <div className="map-frame">
        <AltRoutesMap routes={mapData.routes} bounds={mapData.bounds} />
      </div>
    );
  }
  
  // Case 2: Locations pins (merchants or lockers) are present.
  if (Array.isArray(locations) && locations.length > 0) {
    const center = { lat: locations[0].lat, lng: locations[0].lng ?? locations[0].lon };
    return (
      <div className="map-frame">
        <MerchantMap center={center} merchants={locations} />
      </div>
    );
  }

  // Case 3: Data for a single route or markers.
  if (mapData?.kind) {
     return (
      <div className="map-frame">
        <MapBox payload={mapData} />
      </div>
    );
  }

  // Case 4: A map should be rendered for this step, but the data is not yet available.
  const mapRelatedTools = [
    "check_traffic",
    "calculate_alternative_route",
    "get_nearby_merchants",
    "find_nearby_locker",
  ];
  if (mapRelatedTools.includes(event?.tool)) {
    return (
      <div className="h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20 p-4 text-sm text-[var(--grab-muted)] flex items-center justify-center">
        Map will render once available.
      </div>
    );
  }

  // Default: Don't render anything if no map is expected.
  return null;
}