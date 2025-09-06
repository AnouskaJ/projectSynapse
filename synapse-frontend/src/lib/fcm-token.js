import {
  getMessaging,
  getToken,
  deleteToken,
  isSupported,
} from "firebase/messaging";
import { app } from "./firebase";
import { CFG } from "../config";

const VAPID = CFG.FCM.VAPID_PUBLIC_KEY; // now from env

export async function ensureFreshFcmToken() {
  const supported = await isSupported();
  if (!supported) return null;

  if (Notification.permission !== "granted") {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return null;
  }

  const reg =
    (await navigator.serviceWorker.getRegistration()) ||
    (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

  const messaging = getMessaging(app);
  const tok = await getToken(messaging, {
    vapidKey: VAPID,
    serviceWorkerRegistration: reg,
  });
  return tok || null;
}

export async function refreshFcmToken() {
  const supported = await isSupported();
  if (!supported) return null;

  const reg =
    (await navigator.serviceWorker.getRegistration()) ||
    (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

  const messaging = getMessaging(app);
  try {
    await deleteToken(messaging);
  } catch {}
  const newTok = await getToken(messaging, {
    vapidKey: VAPID,
    serviceWorkerRegistration: reg,
  });
  return newTok || null;
}
