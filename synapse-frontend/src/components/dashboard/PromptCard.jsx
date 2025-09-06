import { useAuth } from "../auth/AuthProvider.jsx";
import { usePrompt } from "../../lib/promptStore";

export default function PromptCard() {
  const { user } = useAuth();
  const [prompt, setPrompt] = usePrompt("");

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
          <button className="btn-sm">View &amp; Edit Prompt</button>
        </div>
      </div>

      {/* textarea */}
      <div className="mt-4 rounded-xl border border-[var(--grab-edge)] p-2 focus-within:border-[var(--grab-accent)] transition">
        <textarea
          value={prompt}
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
