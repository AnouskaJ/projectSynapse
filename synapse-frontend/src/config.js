// Frontend config (reads only from env; no hardcoded keys)
const env =
  (typeof import.meta !== "undefined" && import.meta.env) ||
  (typeof process !== "undefined" && process.env) ||
  {};

const pick = (...keys) => {
  for (const k of keys) {
    const v = env?.[k];
    if (v !== undefined && v !== "") return String(v);
  }
  return undefined;
};

const req = (val, name) => {
  if (!val) throw new Error(`Missing required env var: ${name}`);
  return val;
};

export const CFG = {
  API_BASE:
    pick("VITE_API_BASE", "NEXT_PUBLIC_API_BASE") ||
    (typeof window !== "undefined" ? `${window.location.origin}` : ""),

  MAPS_BROWSER_KEY: req(
    pick("VITE_GOOGLE_MAPS_BROWSER_KEY", "NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY"),
    "VITE_GOOGLE_MAPS_BROWSER_KEY"
  ),

  FIREBASE: {
    apiKey: req(
      pick("VITE_FIREBASE_API_KEY", "NEXT_PUBLIC_FIREBASE_API_KEY"),
      "VITE_FIREBASE_API_KEY"
    ),
    authDomain: req(
      pick("VITE_FIREBASE_AUTH_DOMAIN", "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN"),
      "VITE_FIREBASE_AUTH_DOMAIN"
    ),
    projectId: req(
      pick("VITE_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID"),
      "VITE_FIREBASE_PROJECT_ID"
    ),
    storageBucket: req(
      pick(
        "VITE_FIREBASE_STORAGE_BUCKET",
        "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET"
      ),
      "VITE_FIREBASE_STORAGE_BUCKET"
    ),
    messagingSenderId: req(
      pick(
        "VITE_FIREBASE_MESSAGING_SENDER_ID",
        "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"
      ),
      "VITE_FIREBASE_MESSAGING_SENDER_ID"
    ),
    appId: req(
      pick("VITE_FIREBASE_APP_ID", "NEXT_PUBLIC_FIREBASE_APP_ID"),
      "VITE_FIREBASE_APP_ID"
    ),
    measurementId: pick(
      "VITE_FIREBASE_MEASUREMENT_ID",
      "NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID"
    ),
  },

  FCM: {
    VAPID_PUBLIC_KEY: req(
      pick("VITE_FCM_VAPID", "NEXT_PUBLIC_FCM_VAPID"),
      "VITE_FCM_VAPID"
    ),
    DRY_RUN:
      (pick("VITE_FCM_DRY_RUN", "NEXT_PUBLIC_FCM_DRY_RUN") ?? "false") ===
      "true",
  },

  PROJECT: {
    FIREBASE_PROJECT_ID: req(
      pick("VITE_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID"),
      "VITE_FIREBASE_PROJECT_ID"
    ),
  },

  UI: {
    REQUIRE_AUTH:
      (pick("VITE_REQUIRE_AUTH", "NEXT_PUBLIC_REQUIRE_AUTH") ?? "false") ===
      "true",
    MAX_STEPS: Number(pick("VITE_MAX_STEPS", "NEXT_PUBLIC_MAX_STEPS") ?? 7),
    MAX_SECONDS: Number(
      pick("VITE_MAX_SECONDS", "NEXT_PUBLIC_MAX_SECONDS") ?? 120
    ),
    STREAM_DELAY: Number(
      pick("VITE_STREAM_DELAY", "NEXT_PUBLIC_STREAM_DELAY") ?? 0.1
    ),
    BASELINE_SPEED_KMPH: Number(
      pick("VITE_BASELINE_SPEED_KMPH", "NEXT_PUBLIC_BASELINE_SPEED_KMPH") ??
        40.0
    ),
  },
};

// Convenience named exports
export const firebaseConfig = CFG.FIREBASE;
export const VAPID_PUBLIC_KEY = CFG.FCM.VAPID_PUBLIC_KEY;
export const MAPS_BROWSER_KEY = CFG.MAPS_BROWSER_KEY;
export const API_BASE =
  pick("VITE_API_BASE", "NEXT_PUBLIC_API_BASE") || "http://127.0.0.1:5000";
