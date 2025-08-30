import React from "react";
import { Link } from "react-router-dom";

const services = [
  { key: "grabfood", name: "GrabFood", desc: "Food delivery scenarios" },
  { key: "grabmart", name: "GrabMart", desc: "Mart / inventory scenarios" },
  { key: "grabexpress", name: "GrabExpress", desc: "Parcel dispatch scenarios" },
  { key: "grabcar", name: "GrabCar", desc: "Ride / traffic scenarios" }
];

export default function Home() {
  return (
    <div className="space-y-8">
      <section className="text-center space-y-2">
        <h1 className="text-3xl font-bold" style={{ color: "#00B14F" }}>Project Synapse – Demo</h1>
        <p className="text-gray-300">Pick a service to load a sample, or enter your own scenario.</p>
      </section>

      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {services.map((s) => (
          <Link key={s.key} to={`/service/${s.key}`} className="card hover:brightness-110 transition p-4">
            <div className="text-lg font-semibold" style={{ color: "#00B14F" }}>{s.name}</div>
            <p className="text-sm text-gray-300 mt-1">{s.desc}</p>
            <div className="mt-4">
              <span className="btn btn-ghost">Open</span>
            </div>
          </Link>
        ))}
      </section>

      <section className="text-center">
        <Link to="/custom" className="btn btn-primary">Enter Custom Scenario</Link>
      </section>
    </div>
  );
}
