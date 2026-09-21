importScripts(
  "https://www.gstatic.com/firebasejs/12.5.0/firebase-app-compat.js"
);

importScripts(
  "https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging-compat.js"
);

firebase.initializeApp({
  apiKey: "AIzaSyDJjFmmfavHywB9dfTU18GMFm0T-cyIZUI",
  authDomain: "taxilink-ff936.firebaseapp.com",
  projectId: "taxilink-ff936",
  storageBucket: "taxilink-ff936.firebasestorage.app",
  messagingSenderId: "323311863685",
  appId: "1:323311863685:web:0bd6d156f32ccdc15666ec",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title =
    payload.notification?.title
    || "TaxiLink";

  const options = {
    body:
      payload.notification?.body
      || "You have a new notification.",
    data: payload.data || {},
  };

  self.registration.showNotification(
    title,
    options
  );
});