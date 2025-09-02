import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ScenarioForm from "../components/ScenarioForm.jsx";
import AgentStream from "../components/AgentStream"; 

const DEFAULTS = {
  grabfood: {
    title: "GrabFood",
    scenario: "Order GF-10234 from 'Nasi Goreng House, Velachery' to DLF IT Park, Manapakkam. Kitchen is quoting a 45 minute prep time and the driver is waiting. Proactively inform the customer, minimize driver idle time, and suggest faster nearby alternatives."
  },
  grabmart: {
    title: "GrabMart – Damage Dispute",
    scenario: "Order GM-20987 from 'QuickMart, T. Nagar' to Olympia Tech Park, Guindy. At the doorstep, the customer reports a spilled drink. It's unclear if this is merchant or driver fault. Mediate the dispute fairly on-site."
  },
  grabexpress: {
    title: "GrabExpress",
    scenario: "A valuable parcel is being delivered to Adyar. The driver has arrived but the recipient is not responding. Initiate contact, and if they can't receive it, suggest a safe drop-off or a nearby secure locker."
  },
  grabcar: {
    title: "GrabCar",
    scenario: "An urgent airport ride from SRMIST to Chennai International Airport (MAA) for flight 6E 5119. A major accident is blocking the main route. Find the fastest alternative and inform both passenger and driver."
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

  return (
    <div className="animate-slide-in space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-grab">
          {defaults.title}
        </h2>
        <Link to="/" className="btn btn-ghost text-xs">← Change Scenario</Link>
      </div>

      <ScenarioForm
        defaultScenario={defaults.scenario}
        onRun={(text) => setScenarioText(text)}
        isRunning={!!scenarioText}
      />

      {/* The AgentStream component only renders when a scenario has been submitted */}
      {scenarioText && <AgentStream scenarioText={scenarioText} />}
    </div>
  );
}