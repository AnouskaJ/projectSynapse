/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string
  readonly VITE_GOOGLE_MAPS_BROWSER_KEY: string

  readonly VITE_FIREBASE_API_KEY: string
  readonly VITE_FIREBASE_AUTH_DOMAIN: string
  readonly VITE_FIREBASE_PROJECT_ID: string
  readonly VITE_FIREBASE_STORAGE_BUCKET: string
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID: string
  readonly VITE_FIREBASE_APP_ID: string
  readonly VITE_FIREBASE_MEASUREMENT_ID?: string

  readonly VITE_FCM_VAPID: string

  readonly VITE_REQUIRE_AUTH?: string
  readonly VITE_MAX_STEPS?: string
  readonly VITE_MAX_SECONDS?: string
  readonly VITE_STREAM_DELAY?: string
  readonly VITE_BASELINE_SPEED_KMPH?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
