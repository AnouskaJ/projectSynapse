// simple, app-wide prompt persistence
const KEY = "synapse.prompt";

export function loadPrompt() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function savePrompt(text) {
  try {
    localStorage.setItem(KEY, text ?? "");
  } catch {}
}

// React helper (optional, used in Home)
import { useEffect, useState } from "react";
export function usePrompt(initial = "") {
  const [prompt, setPrompt] = useState(() => loadPrompt() || initial);
  useEffect(() => {
    savePrompt(prompt);
  }, [prompt]);
  return [prompt, setPrompt];
}
