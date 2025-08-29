import React from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Scenario from "./pages/Scenario.jsx";

const grabGreen = "#00B14F";

function Shell({ children }) {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen bg-grab-bg text-white">
      <header className="sticky top-0 z-10 border-b border-grab-edge backdrop-blur bg-grab-bg/70">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="font-bold tracking-tight" style={{ color: grabGreen }}>
            Project Synapse
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            <Link to="/" className={`btn btn-ghost ${pathname === "/" ? "opacity-100" : "opacity-70"}`}>Home</Link>
            <a className="btn btn-ghost opacity-70" href="https://github.com" target="_blank" rel="noreferrer">GitHub</a>
            <span className="text-xs text-gray-400 hidden sm:inline">Dark Mode • Grab Green</span>
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6">{children}</main>
      <footer className="max-w-6xl mx-auto px-4 py-10 text-center text-gray-400">
        Built for a Synapse demo • <span style={{ color: grabGreen }}>Grab</span> styling
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        {/* Single scenario page that adapts by service */}
        <Route path="/service/:service" element={<Scenario />} />
        {/* Optional fully custom path */}
        <Route path="/custom" element={<Scenario isCustom />} />
        {/* Fallback */}
        <Route path="*" element={<Home />} />
      </Routes>
    </Shell>
  );
}
