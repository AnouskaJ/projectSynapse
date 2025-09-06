/* /public/firebase-messaging-sw.js
   Service Worker for Firebase Cloud Messaging + manual notifications
   - Shows notifications for background FCM messages
   - Lets pages postMessage({ type: "SHOW_NOTIFICATION", ... }) to display a system notification
   - Focuses an existing tab (or opens one) on notification click
*/

// ---- Firebase (compat is simplest for SWs) ---------------------------------
importScripts(
  "https://www.gstatic.com/firebasejs/10.11.0/firebase-app-compat.js"
);
importScripts(
  "https://www.gstatic.com/firebasejs/10.11.0/firebase-messaging-compat.js"
);

// === YOUR PROJECT CONFIG ===
firebase.initializeApp({
  apiKey: "AIzaSyDOlod9mcpsqWJdalalPka7CbAhOvHN6Jo",
  authDomain: "synapse-54cfb.firebaseapp.com",
  projectId: "synapse-54cfb",
  storageBucket: "synapse-54cfb.firebasestorage.app",
  messagingSenderId: "844442984824",
  appId: "1:844442984824:web:252a836b759d196a65e88d",
  measurementId: "G-D3NW1C1JXZ",
});

const messaging = firebase.messaging();

// Make this SW take control ASAP (helps dev)
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

// ---- 1) Background FCM handler --------------------------------------------
// If you send FCM v1 messages with `webpush.notification`, `payload.notification` is present.
messaging.onBackgroundMessage((payload) => {
  const n = payload?.notification || {};
  const title = n.title || "Notification";
  const options = {
    body: n.body || "You have a new update",
    icon: "/icon-192x192.png", // ensure these exist in /public
    badge: "/icon-96x96.png",
    data: payload?.data || {}, // keep extra data for click handling
    // tag: "grabcar",           // uncomment to collapse duplicates
  };
  self.registration.showNotification(title, options);
});

// ---- 2) Manual notifications from the page --------------------------------
// Your page can do: navigator.serviceWorker.controller.postMessage({ type:"SHOW_NOTIFICATION", title, options })
self.addEventListener("message", (e) => {
  const data = e?.data || {};
  if (data.type === "SHOW_NOTIFICATION") {
    const title = data.title || "Notification";
    const options = data.options || {};
    // make sure icons are set if not provided
    options.icon = options.icon || "/icon-192x192.png";
    options.badge = options.badge || "/icon-96x96.png";
    self.registration.showNotification(title, options);
  }
});

// ---- 3) Hardening: handle bare Push payloads (just in case) ---------------
// Some providers may deliver raw push events without going through FCM helpers.
self.addEventListener("push", (event) => {
  // If FCM already handled it, this may not fire; harmless fallback.
  if (!event.data) return;
  let data = {};
  try {
    data = event.data.json();
  } catch {
    data = { body: event.data.text() };
  }

  // Common places where a title/body might live
  const title =
    data.title ||
    data.notification?.title ||
    data.webpush?.notification?.title ||
    "Notification";

  const body =
    data.body ||
    data.notification?.body ||
    data.webpush?.notification?.body ||
    "";

  const options = {
    body,
    icon:
      data.icon ||
      data.notification?.icon ||
      data.webpush?.notification?.icon ||
      "/icon-192x192.png",
    badge:
      data.badge ||
      data.notification?.badge ||
      data.webpush?.notification?.badge ||
      "/icon-96x96.png",
    data: data.data || data, // keep whatever came with the push
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// ---- 4) Click handling: focus or open the app ------------------------------
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  // Deep link if provided (set as data.link in your payload/options)
  const targetUrl =
    (event.notification &&
      event.notification.data &&
      event.notification.data.link) ||
    "/";

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        // focus an existing tab if we have one
        for (const client of clientList) {
          const url = new URL(client.url || "/", self.location.origin);
          if (url.origin === self.location.origin) {
            if ("focus" in client) return client.focus();
          }
        }
        // otherwise open a new tab
        if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
      })
  );
});
