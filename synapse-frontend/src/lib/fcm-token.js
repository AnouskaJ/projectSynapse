// src/lib/fcm-token.js
import { getMessaging, getToken, deleteToken, isSupported } from "firebase/messaging";
import { app } from "../lib/firebase";

const VAPID = "BKCnh74gURGvjrBN-dB7HaxMPqrSfrNHe7bm1MNbDqxPN9IZsVkVhmNL8fhc_zkgoTlx8ywKg9T5NExxT_0WjHw"; // from Firebase console

export async function ensureFreshFcmToken() {
  const supported = await isSupported();
  if (!supported) return null;

  if (Notification.permission !== "granted") {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return null;
  }

  const reg = (await navigator.serviceWorker.getRegistration()) ||
              (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

  const messaging = getMessaging(app);

  // getToken is idempotent; it returns the latest valid token for this SW scope
  const tok = await getToken(messaging, { vapidKey: VAPID, serviceWorkerRegistration: reg });
  return tok || null;
}

// If FCM returns UNREGISTERED, call this to rotate the token
export async function refreshFcmToken() {
  const supported = await isSupported();
  if (!supported) return null;

  const reg = (await navigator.serviceWorker.getRegistration()) ||
              (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

  const messaging = getMessaging(app);
  try { await deleteToken(messaging); } catch {}
  const newTok = await getToken(messaging, { vapidKey: VAPID, serviceWorkerRegistration: reg });
  return newTok || null;
}
