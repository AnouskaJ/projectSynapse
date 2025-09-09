import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthProvider.jsx";
import { usePrompt } from "../../lib/promptStore";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react"; // icon library

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
  const navigate = useNavigate();

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
      <div className="mb-4">
        <h1 className="text-2xl font-semibold text-[var(--grab-accent)]">
          Enter Scenario Prompt
        </h1>
        <p className="text-sm text-[var(--grab-muted)]">
          Describe your scenario and click the arrow to continue
        </p>
      </div>

      {/* textarea with action button inside */}
      <div className="relative mt-2 rounded-xl border border-[var(--grab-edge)] focus-within:border-[var(--grab-accent)] transition">
        <textarea
          value={prompt + (interim ? ` ${interim}` : "")}
          onChange={(e) => setPrompt(e.target.value)}
          rows={8}
          placeholder="Enter a scenario prompt…"
          className="w-full resize-y rounded-lg bg-black p-3 pr-10 outline-none placeholder:text-neutral-500 min-h-[180px]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              go();
            }
          }}
        />
        {/* arrow button */}
        <button
          type="button"
          onClick={go}
          className="absolute bottom-3 right-3 p-2 rounded-full bg-[var(--grab-accent)] hover:bg-[var(--grab-accent-dark)] transition"
          title="Go"
        >
          <ChevronRight className="w-5 h-5 text-white" />
        </button>
      </div>

      <div className="mt-2 text-xs text-[var(--grab-muted)]">
        Agent will use this prompt to plan step-by-step actions.
      </div>
    </section>
  );
}
