import React from "react";

export default function ViewToggle({ mode, setMode }) {
  const isGUI = mode === "gui";

  return (
    <div className="w-[220px] rounded-full border border-[var(--grab-edge)] bg-black/20 p-1 relative select-none">
      <div
        className={`absolute top-1 bottom-1 w-[108px] rounded-full transition-transform ${
          isGUI ? "translate-x-1" : "translate-x-[109px]"
        }`}
        style={{ background: "linear-gradient(90deg,#0c1511,#14231c)" }}
      />
      <div className="relative z-10 grid grid-cols-2 text-xs font-medium">
        <button className={`py-1.5 ${isGUI ? "text-white" : "text-gray-400"}`} onClick={() => setMode("gui")}>
          GUI Chain
        </button>
        <button className={`py-1.5 ${!isGUI ? "text-white" : "text-gray-400"}`} onClick={() => setMode("cli")}>
          CLI Chain
        </button>
      </div>
    </div>
  );
}
