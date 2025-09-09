import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthProvider.jsx";
import { usePrompt } from "../../lib/promptStore";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";

export default function PromptCard() {
  const { user } = useAuth();
  const [prompt, setPrompt] = usePrompt("");
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef(null);
  const navigate = useNavigate();

  // --- Speech (dictation) wiring ---
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const rec = new SR();
    rec.lang = "en-IN";       // adjust if needed
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

  // --- Continue action (save + navigate) ---
  const go = () => {
    const v = (prompt || "").trim();
    if (!v) return;
    try {
      localStorage.setItem("synapse.prompt", v);
      localStorage.setItem("synapse.prompt_grabcar", v);
    } catch {}
    navigate("/service/agent");
  };

  return (
    <section className="surface-strong edge-accent-soft p-5 rounded-2xl border border-[var(--grab-edge)] shadow-md">
      {/* title row */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--grab-accent)]">
            Enter Scenario Prompt
          </h1>
          <p className="text-sm text-[var(--grab-muted)]">
            Describe your scenario and click the arrow to continue
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
            title={isListening ? "Stop dictation" : "Start dictation"}
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
        </div>
      </div>

      {/* textarea with inline arrow action */}
      <div className="relative mt-2 rounded-xl border border-[var(--grab-edge)] focus-within:border-[var(--grab-accent)] transition">
        <textarea
          value={prompt + (interim ? ` ${interim}` : "")}
          onChange={(e) => setPrompt(e.target.value)}
          rows={8}
          placeholder="Enter a scenario prompt…"
          className="w-full resize-y rounded-lg bg-black p-3 pr-12 outline-none placeholder:text-neutral-500 min-h-[180px]"
          onKeyDown={(e) => {
            // Cmd/Ctrl + Enter to continue
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              go();
            }
          }}
        />
        <button
          type="button"
          onClick={go}
          className="absolute bottom-3 right-3 p-2 rounded-full bg-[var(--grab-accent)] hover:bg-[var(--grab-accent-dark)] transition"
          title="Go"
          aria-label="Continue"
        >
          <ChevronRight className="w-5 h-5 text-white" />
        </button>
      </div>

      {/* caption */}
      <div className="mt-2 text-right text-xs text-[var(--grab-muted)]">
        Agent will use this prompt to plan step-by-step actions.
      </div>
    </section>
  );
}
