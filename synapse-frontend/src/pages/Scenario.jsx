import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ScenarioForm from "../components/ScenarioForm.jsx";
import AgentStream from "../components/AgentStream.jsx";

/**
 * Agency/dispatcher voice with concrete context for parsers.
 */
const DEFAULTS = {
  grabfood: {
    title: "GrabFood",
    scenario: [
      "We’re coordinating order GF-10234 from “Nasi Goreng House, Velachery” to the customer at DLF IT Park, Manapakkam (mode: two-wheeler).",
      "Kitchen is currently quoting ~40–45 minutes and the backlog is growing. The driver is already waiting at the merchant.",
      "Keep the customer proactively informed about the delay, minimize the driver’s idle time, and—if on-time delivery looks at risk—surface 2–3 similar nearby restaurants with faster prep as potential switches.",
      "Route context: from Nasi Goreng House, Velachery → DLF IT Park, Manapakkam."
    ].join(" ")
  },

  // UPDATED: GrabMart now uses the “Damaged Packaging Dispute” scenario
  grabmart: {
    title: "GrabMart – Doorstep Damage Dispute",
    scenario: [
      "We’re handling order GM-20987 picked up from “QuickMart, T. Nagar” and delivered to the customer at Olympia Tech Park, Guindy (mode: two-wheeler).",
      "At the doorstep, the customer reports a spilled drink. It isn’t clear if this came from poor packaging at the store or something that happened during transit.",
      "We need a quick, fair resolution on-site that doesn’t unfairly penalize the driver while still giving the customer a smooth experience. Collect clear photos from both sides and brief answers to seal/handling questions, then close the loop with a transparent outcome and share it with both parties.",
      "Route context: QuickMart, T. Nagar → Olympia Tech Park, Guindy."
    ].join(" ")
  },

  grabexpress: {
    title: "GrabExpress",
    scenario: [
      "Valuable parcel pickup at Phoenix Marketcity, Velachery with drop at House No. 12, 3rd Main Road, Adyar (mode: two-wheeler).",
      "Driver reached the destination but the recipient isn’t responding. The building only accepts clearly labelled packages.",
      "Reach the recipient via chat for instructions. If they authorize a safe drop (e.g., concierge) proceed accordingly; otherwise suggest a secure nearby locker and coordinate a revised handoff.",
      "Route context: Phoenix Marketcity, Velachery → 3rd Main Road, Adyar."
    ].join(" ")
  },

  grabcar: {
    title: "GrabCar",
    scenario: [
      "Urgent airport ride from SRMIST to Chennai International Airport (MAA), mode: drive.",
      "Major accident reported near Tambaram causing heavy congestion on the usual route.",
      "Identify the fastest alternate path right now and share the updated ETA with both the passenger and driver. Passenger’s flight is 6E 5119 at 22:30—if that flight is delayed, communicate it to ease anxiety.",
      "Route context: SRMIST → Chennai International Airport (MAA)."
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
