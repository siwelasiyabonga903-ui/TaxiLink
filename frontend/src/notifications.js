import {
  getToken,
  onMessage,
} from "firebase/messaging";

import api from "./api/client";

import {
  firebaseVapidKey,
  getFirebaseMessaging,
} from "./firebase";


export async function registerPushNotifications() {
  if (
    !("Notification" in window) ||
    !("serviceWorker" in navigator)
  ) {
    return {
      registered: false,
      reason: "unsupported",
    };
  }

  const permission =
    await Notification.requestPermission();

  if (permission !== "granted") {
    return {
      registered: false,
      reason: "permission-denied",
    };
  }

  const messaging =
    await getFirebaseMessaging();

  if (!messaging) {
    return {
      registered: false,
      reason: "messaging-unsupported",
    };
  }

  const serviceWorkerRegistration =
    await navigator.serviceWorker.register(
      "/firebase-messaging-sw.js"
    );

  const token = await getToken(
    messaging,
    {
      vapidKey: firebaseVapidKey,
      serviceWorkerRegistration,
    }
  );

  if (!token) {
    return {
      registered: false,
      reason: "no-token",
    };
  }

  await api.post(
    "/transport/device-tokens/",
    {
      token,
      platform: "WEB",
    }
  );

  return {
    registered: true,
  };
}


export async function listenForForegroundNotifications() {
  if (
    !("Notification" in window) ||
    !("serviceWorker" in navigator) ||
    Notification.permission !== "granted"
  ) {
    return () => {};
  }

  const messaging =
    await getFirebaseMessaging();

  if (!messaging) {
    return () => {};
  }

  const unsubscribe = onMessage(
    messaging,
    async (payload) => {
      const title =
        payload.notification?.title
        || "TaxiLink";

      const options = {
        body:
          payload.notification?.body
          || "You have a new notification.",
        data: payload.data || {},
      };

      const registration =
        await navigator.serviceWorker.ready;

      await registration.showNotification(
        title,
        options
      );
    }
  );

  return unsubscribe;
}