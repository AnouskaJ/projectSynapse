import { useEffect, useState } from "react";

export function useLocalPrompt(key) {
  const storageKey = `synapse.prompt.${key}`;
  const [prompt, setPrompt] = useState(() => localStorage.getItem(storageKey) || "");

  useEffect(() => { localStorage.setItem(storageKey, prompt || ""); }, [prompt, storageKey]);

  return [prompt, setPrompt];
}
