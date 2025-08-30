// /public/firebase-messaging-sw.js
// Firebase compat is simplest for SWs
importScripts("https://www.gstatic.com/firebasejs/10.11.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.11.0/firebase-messaging-compat.js");

// === YOUR PROJECT CONFIG ===
firebase.initializeApp({
  apiKey: "AIzaSyDOlod9mcpsqWJdalalPka7CbAhOvHN6Jo",
  authDomain: "synapse-54cfb.firebaseapp.com",
  projectId: "synapse-54cfb",
  storageBucket: "synapse-54cfb.firebasestorage.app",
  messagingSenderId: "844442984824",
  appId: "1:844442984824:web:252a836b759d196a65e88d",
  measurementId: "G-D3NW1C1JXZ"
});

const messaging = firebase.messaging();

// Show a system notification when a BACKGROUND message arrives
messaging.onBackgroundMessage((payload) => {
  // FCM v1 with webpush.notification will populate payload.notification
  const n = payload.notification || {};
  const title = n.title || "Notification";
  const options = {
    body: n.body || "You have a new update",
    icon: "/icon-192x192.png",            // optional; ensure this file exists
    data: payload.data || {},             // keep data for click handling
    badge: "/icon-96x96.png",             // optional
  };
  self.registration.showNotification(title, options);
});

// Optional: open your app when the user clicks the notification
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification?.data && event.notification.data.link) || "/";
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
    for (const client of clientList) {
      if ("focus" in client) return client.focus();
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});
