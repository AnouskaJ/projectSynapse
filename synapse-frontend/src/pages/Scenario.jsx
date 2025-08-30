import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ScenarioForm from "../components/ScenarioForm.jsx";
import AgentStream from "../components/AgentStream.jsx";

/**
 * Each scenario is phrased to:
 *  - clearly indicate the problem category (merchant_capacity, recipient_unavailable, traffic)
 *  - include plain-text origin/destination with “from … to …” when relevant
 *  - include mode hints like “mode drive / two-wheeler / bicycle / walk”
 *  - give enough context for tools: notify_*(), get_merchant_status(), calculate_alternative_route(), etc.
 */
const DEFAULTS = {
  grabfood: {
    title: "GrabFood",
    scenario: [
      "Overloaded restaurant. Order GF-10234 at “Nasi Goreng House, Velachery”.",
      "Kitchen reports prep time around 45 minutes (backlog growing).",
      "Driver is already waiting at the merchant; customer is near DLF IT Park, Manapakkam.",
      "Ask to minimize driver idle time and keep the customer informed.",
      "Plan:",
      "- Proactively notify customer about the long wait and offer a small voucher.",
      "- If feasible, temporarily reassign the driver to a short nearby drop while food is prepared.",
      "- If delay is critical, suggest 2–3 nearby, similar restaurants with shorter prep times.",
      "Notes: origin_place: Nasi Goreng House, Velachery; dest_place: DLF IT Park, Manapakkam."
    ].join(" ")
  },

  grabmart: {
    title: "GrabMart",
    scenario: [
      "Mart inventory shortage. Order GM-55871 at “QuickMart, OMR Navalur”.",
      "Two items out of stock (almond milk 1L, brown bread).",
      "Customer prefers fastest resolution over perfect substitutions.",
      "Ask to propose best substitutions and nearest alternate marts if needed, then notify the customer.",
      "Notes: origin_place: QuickMart, OMR Navalur; dest_place: Hiranandani, Egattur."
    ].join(" ")
  },

  grabexpress: {
    title: "GrabExpress",
    scenario: [
      "Recipient unavailable for valuable parcel delivery.",
      "Driver arrived at “House No. 12, 3rd Main Road, Adyar” but recipient isn’t picking up.",
      "Building concierge accepts labelled packages only.",
      "Ask to start chat, suggest a safe drop if approved, else find a nearby secure locker.",
      "Notes: origin_place: Phoenix Marketcity, Velachery; dest_place: Adyar 3rd Main Road."
    ].join(" ")
  },

  grabcar: {
    title: "GrabCar",
    scenario: [
      "Sudden major traffic obstruction.",
      "Passenger is on an urgent airport trip from SRMIST to Chennai International Airport (MAA); mode drive.",
      "Accident reported near Tambaram causing heavy congestion on the usual route.",
      "Need the fastest alternate route immediately and notify both driver and passenger with the new ETA.",
      "Passenger’s flight: 6E 5119 at 22:30 (if delayed, mention to reduce anxiety).",
      "Request: check traffic, re-calculate route, then notify_passenger_and_driver.",
      "from SRMIST to Chennai airport, mode drive."
    ].join(" ")
  },

  custom: {
    title: "Custom",
    scenario: ""
  }
};

export default function Scenario({ isCustom = false }) {
  const { service } = useParams();
  const key = isCustom ? "custom" : (service || "grabcar").toLowerCase();
  const defaults = DEFAULTS[key] ?? DEFAULTS.custom;

  const [scenarioText, setScenarioText] = useState("");

  const headline = useMemo(() => defaults.title || "Scenario", [defaults.title]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold" style={{ color: "#00B14F" }}>
          {headline} Scenario
        </h2>
        <Link to="/" className="btn btn-ghost">← Back</Link>
      </div>

      <ScenarioForm
        defaultScenario={defaults.scenario}
        onRun={(text) => setScenarioText(text)}
      />

      <AgentStream scenarioText={scenarioText} />
    </div>
  );
}
