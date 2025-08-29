/* global importScripts, firebase */
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');


firebase.initializeApp({
apiKey: 'YOUR_WEB_API_KEY',
projectId: 'YOUR_PROJECT_ID',
messagingSenderId: 'YOUR_SENDER_ID',
appId: 'YOUR_APP_ID'
});


const messaging = firebase.messaging();


// Optional: show background notifications
messaging.onBackgroundMessage((payload) => {
const title = payload?.notification?.title || 'Synapse';
const body = payload?.notification?.body || '';
self.registration.showNotification(title, { body });
});