import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthProvider.jsx";
import { usePrompt } from "../../lib/promptStore";

export default function PromptCard() {
  const { user } = useAuth();
  const [prompt, setPrompt] = usePrompt("");
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef(null);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const rec = new SR();
    rec.lang = "en-IN"; // adjust language if needed
    rec.interimResults = true;
    rec.continuous = true;

    rec.onresult = (e) => {
      let interimText = "";
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t + " ";
        else interimText += t + " ";
      }
      if (finalText) {
        setPrompt((prev) => (prev ? prev + " " : "") + finalText.trim());
      }
      setInterim(interimText.trim());
    };

    rec.onend = () => {
      setIsListening(false);
      setInterim("");
    };

    recognitionRef.current = rec;
    return () => {
      try {
        rec.stop();
      } catch {}
    };
  }, [setPrompt]);

  const toggleMic = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (isListening) {
      rec.stop();
      setIsListening(false);
    } else {
      try {
        rec.start();
        setIsListening(true);
        setInterim("");
      } catch {}
    }
  };

  return (
    <section className="surface-strong edge-accent-soft p-4 md:p-5">
      {/* title row */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--grab-accent)]">
            Enter Scenario Prompt
          </h1>
          <p className="text-sm text-[var(--grab-muted)]">
            Describe your scenario and choose a service to continue
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Mic button */}
          <button
            type="button"
            onClick={toggleMic}
            className={`btn-sm flex items-center gap-2 ${
              isListening ? "ring-2 ring-red-500" : ""
            }`}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`h-4 w-4 ${isListening ? "animate-pulse" : ""}`}
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3z" />
              <path d="M5 11a1 1 0 1 0-2 0 9 9 0 0 0 8 8.94V22a1 1 0 1 0 2 0v-2.06A9 9 0 0 0 21 11a1 1 0 1 0-2 0 7 7 0 0 1-14 0z" />
            </svg>
            {isListening ? "Listening…" : "Dictate"}
          </button>

          <button className="btn-sm">View &amp; Edit Prompt</button>
        </div>
      </div>

      {/* textarea */}
      <div className="mt-4 rounded-xl border border-[var(--grab-edge)] p-2 focus-within:border-[var(--grab-accent)] transition">
        <textarea
          value={prompt + (interim ? ` ${interim}` : "")}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          placeholder="Enter a scenario prompt…"
          className="w-full resize-y rounded-lg bg-black p-3 outline-none placeholder:text-neutral-500"
        />
      </div>

      {/* caption */}
      <div className="mt-2 text-right text-xs text-[var(--grab-muted)]">
        Agent will use this prompt to plan step-by-step actions.
      </div>
    </section>
  );
}
