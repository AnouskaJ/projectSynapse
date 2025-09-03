// src/config.js
// Frontend config (safe to ship to the browser).
// You can override any of these via env vars:
//  - Vite: VITE_*
//  - Next.js: NEXT_PUBLIC_*

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

export const CFG = {
  // If you have a public API base, set VITE_API_BASE or NEXT_PUBLIC_API_BASE
  API_BASE:
    pick("VITE_API_BASE", "NEXT_PUBLIC_API_BASE") ||
    (typeof window !== "undefined" ? `${window.location.origin}` : ""),

  // Google Maps **browser** key (NOT server web-services key)
  MAPS_BROWSER_KEY:
    pick("VITE_GOOGLE_MAPS_BROWSER_KEY", "NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY") ||
    // fallback to the value you shared
    "AIzaSyD-Kgac_rhTumRaqKN4DiZg9GZnKtDIJTk",

  // Firebase web config (safe for client)
  FIREBASE: {
    apiKey:
      pick("VITE_FIREBASE_API_KEY", "NEXT_PUBLIC_FIREBASE_API_KEY") ||
      "AIzaSyDOlod9mcpsqWJdalalPka7CbAhOvHN6Jo",
    authDomain:
      pick("VITE_FIREBASE_AUTH_DOMAIN", "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN") ||
      "synapse-54cfb.firebaseapp.com",
    projectId:
      pick("VITE_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID") ||
      "synapse-54cfb",
    storageBucket:
      pick("VITE_FIREBASE_STORAGE_BUCKET", "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET") ||
      "synapse-54cfb.firebasestorage.app",
    messagingSenderId:
      pick("VITE_FIREBASE_MESSAGING_SENDER_ID", "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID") ||
      "844442984824",
    appId:
      pick("VITE_FIREBASE_APP_ID", "NEXT_PUBLIC_FIREBASE_APP_ID") ||
      "1:844442984824:web:252a836b759d196a65e88d",
    measurementId:
      pick("VITE_FIREBASE_MEASUREMENT_ID", "NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID") ||
      "G-D3NW1C1JXZ",
  },

  // Web Push (public VAPID key is safe to expose)
  FCM: {
    VAPID_PUBLIC_KEY:
      pick("VITE_FCM_VAPID", "NEXT_PUBLIC_FCM_VAPID") ||
      "BKCnh74gURGvjrBN-dB7HaxMPqrSfrNHe7bm1MNbDqxPN9IZsVkVhmNL8fhc_zkgoTlx8ywKg9T5NExxT_0WjHw",
    DRY_RUN: (pick("VITE_FCM_DRY_RUN", "NEXT_PUBLIC_FCM_DRY_RUN") ?? "false") === "true",
  },

  // Project/meta
  PROJECT: {
    FIREBASE_PROJECT_ID:
      pick("VITE_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID") ||
      "synapse-54cfb",
  },

  // UI/runtime knobs (browser-side)
  UI: {
    REQUIRE_AUTH: (pick("VITE_REQUIRE_AUTH", "NEXT_PUBLIC_REQUIRE_AUTH") ?? "false") === "true",
    MAX_STEPS: Number(pick("VITE_MAX_STEPS", "NEXT_PUBLIC_MAX_STEPS") ?? 7),
    MAX_SECONDS: Number(pick("VITE_MAX_SECONDS", "NEXT_PUBLIC_MAX_SECONDS") ?? 120),
    STREAM_DELAY: Number(pick("VITE_STREAM_DELAY", "NEXT_PUBLIC_STREAM_DELAY") ?? 0.10),
    BASELINE_SPEED_KMPH: Number(
      pick("VITE_BASELINE_SPEED_KMPH", "NEXT_PUBLIC_BASELINE_SPEED_KMPH") ?? 40.0
    ),
  },
};

// Named exports if you prefer importing them directly
export const firebaseConfig = CFG.FIREBASE;
export const VAPID_PUBLIC_KEY = CFG.FCM.VAPID_PUBLIC_KEY;
export const MAPS_BROWSER_KEY = CFG.MAPS_BROWSER_KEY;
export const API_BASE = "http://127.0.0.1:5000";
