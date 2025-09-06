import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../components/auth/AuthProvider.jsx";
import HeaderNav from "../components/ui/HeaderNav.jsx";
import FooterPills from "../components/ui/FooterPills.jsx";

export default function Login() {
  const { login, reset, user, ready } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const nav = useNavigate();
  const loc = useLocation();
  const backTo =
    (loc.state && loc.state.from && loc.state.from.pathname) || "/";

  useEffect(() => {
    if (ready && user) nav(backTo, { replace: true });
  }, [ready, user, backTo, nav]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err?.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function onForgot() {
    if (!email) return setError("Enter your email to receive a reset link.");
    setError("");
    try {
      await reset(email.trim());
      alert("Reset link sent. Check your email.");
    } catch (err) {
      setError(err?.message || "Could not send reset email");
    }
  }

  const field =
    "flex items-center gap-3 rounded-xl border border-[var(--grab-edge)] bg-[var(--grab-panel)] px-3 py-2 focus-within:border-[var(--grab-accent)]";
  const label = "text-sm text-[var(--grab-muted)]";

  return (
    <div className="min-h-screen flex flex-col bg-[var(--grab-bg)] text-white">
      {/* Header */}
      <HeaderNav />

      {/* Main content */}
      <div className="flex flex-1 items-center justify-center px-4">
        <form
          onSubmit={onSubmit}
          className="w-full mt-5 max-w-sm rounded-2xl border border-[var(--grab-edge)] bg-[var(--grab-panel)]/80 px-5 py-6 shadow"
        >
          {/* heading */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Sign in</h2>
            <span className="rounded-full border border-[var(--grab-edge)]/70 px-2 py-0.5 text-xs opacity-80">
              Live • Secure
            </span>
          </div>

          <div className="mt-3 border-t border-[var(--grab-edge)]" />

          {error && (
            <div className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="mt-4 space-y-3">
            <label className="block space-y-1">
              <span className={label}>Email</span>
              <div className={field}>
                <span className="opacity-70">✉️</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  autoComplete="email"
                  className="w-full bg-transparent outline-none placeholder:text-neutral-500 text-sm"
                />
              </div>
            </label>

            <label className="block space-y-1">
              <span className={label}>Password</span>
              <div className={field}>
                <span className="opacity-70">🔒</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full bg-transparent outline-none placeholder:text-neutral-500 text-sm"
                />
              </div>
            </label>

            <div className="flex items-center justify-between text-xs">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="h-3 w-3 rounded border border-[var(--grab-edge)] bg-transparent"
                />
                <span className="text-[var(--grab-muted)]">Remember me</span>
              </label>
              <button
                type="button"
                onClick={onForgot}
                className="text-[var(--grab-link)] hover:underline"
              >
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 w-full rounded-lg bg-[var(--grab-accent)] py-2 font-medium text-black disabled:opacity-60 text-sm"
            >
              {busy ? "Signing in..." : "Continue"}
            </button>

            <div className="relative my-2 text-center">
              <span className="absolute inset-x-0 top-1/2 -translate-y-1/2 border-t border-[var(--grab-edge)]" />
              <span className="relative bg-[var(--grab-panel)]/80 px-2 text-xs text-[var(--grab-muted)]">
                or
              </span>
            </div>

            <button
              type="button"
              aria-disabled="true"
              className="w-full rounded-lg border border-[var(--grab-edge)] bg-transparent py-2 text-sm font-medium opacity-85 hover:opacity-100"
            >
              <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full border border-[var(--grab-edge)] align-middle" />
              Continue with Google
            </button>

            <p className="pt-1 text-center text-xs text-[var(--grab-muted)]">
              By continuing, you agree to our{" "}
              <span className="text-[var(--grab-link)]">Terms</span> and{" "}
              <span className="text-[var(--grab-link)]">Privacy Policy</span>.
            </p>
          </div>
        </form>
      </div>

      {/* Footer */}
      <FooterPills />
    </div>
  );
}
