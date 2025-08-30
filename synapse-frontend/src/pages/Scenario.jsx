import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ScenarioForm from "../components/ScenarioForm.jsx";
import AgentStream from "../components/AgentStream.jsx";

const DEFAULTS = {
  grabfood: {
    title: "GrabFood",
    scenario: "Restaurant overloaded: kitchen prep time exceeds 40 minutes. Customer waiting."
  },
  grabmart: {
    title: "GrabMart",
    scenario: "Mart inventory shortage: ordered items out of stock. Suggest substitutions and nearest alternatives."
  },
  grabexpress: {
    title: "GrabExpress",
    scenario: "Road closure due to parade. Parcel must be rerouted, driver stuck."
  },
  grabcar: {
    title: "GrabCar",
    scenario: "Traffic jam en route to airport caused by accident. Need fastest alternate route."
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
        <h2 className="text-2xl font-bold" style={{ color: "#00B14F" }}>{headline} Scenario</h2>
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
