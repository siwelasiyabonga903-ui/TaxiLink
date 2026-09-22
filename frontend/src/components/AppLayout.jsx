import {
  useEffect,
  useState,
} from "react";

import {
  NavLink,
  useNavigate,
} from "react-router-dom";

import PassengerLocationMonitor
  from "./PassengerLocationMonitor";

import { useAuth } from "../context/AuthContext";

import {
  listenForForegroundNotifications,
  registerPushNotifications,
} from "../notifications";


const NOTIFICATION_RETRY_DELAY_MS = 15000;


export default function AppLayout({
  children,
}) {
  const { user, logout } = useAuth();

  const navigate = useNavigate();

  const [
    notificationState,
    setNotificationState,
  ] = useState("idle");


  useEffect(() => {
    let cancelled = false;
    let retryTimer = null;
    let permissionListenersActive = false;


    function removePermissionListeners() {
      if (!permissionListenersActive) {
        return;
      }

      document.removeEventListener(
        "pointerdown",
        handlePermissionGesture,
        true
      );

      document.removeEventListener(
        "keydown",
        handlePermissionGesture,
        true
      );

      permissionListenersActive = false;
    }


    function scheduleRetry() {
      if (cancelled || retryTimer !== null) {
        return;
      }

      retryTimer = window.setTimeout(
        () => {
          retryTimer = null;
          startRegistration();
        },
        NOTIFICATION_RETRY_DELAY_MS
      );
    }


    async function startRegistration() {
      if (cancelled) {
        return;
      }

      setNotificationState("loading");

      try {
        const result =
          await registerPushNotifications();

        if (cancelled) {
          return;
        }

        if (result.registered) {
          setNotificationState("enabled");
          return;
        }

        if (
          result.reason
          === "permission-denied"
        ) {
          setNotificationState(
            Notification.permission === "denied"
              ? "denied"
              : "idle"
          );

          return;
        }

        setNotificationState("unavailable");
      } catch (error) {
        if (cancelled) {
          return;
        }

        console.error(
          "Notification registration failed:",
          error
        );

        setNotificationState("error");

        if (
          Notification.permission
          === "granted"
        ) {
          scheduleRetry();
        }
      }
    }


    function handlePermissionGesture() {
      removePermissionListeners();
      startRegistration();
    }


    if (
      !("Notification" in window)
      || !("serviceWorker" in navigator)
    ) {
      setNotificationState("unavailable");
    } else if (
      Notification.permission === "granted"
    ) {
      startRegistration();
    } else if (
      Notification.permission === "denied"
    ) {
      setNotificationState("denied");
    } else {
      permissionListenersActive = true;

      document.addEventListener(
        "pointerdown",
        handlePermissionGesture,
        {
          once: true,
          capture: true,
        }
      );

      document.addEventListener(
        "keydown",
        handlePermissionGesture,
        {
          once: true,
          capture: true,
        }
      );
    }


    return () => {
      cancelled = true;

      removePermissionListeners();

      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [user.username]);


  useEffect(() => {
    if (
      notificationState !== "enabled"
    ) {
      return undefined;
    }

    let cancelled = false;
    let unsubscribe = () => {};


    const startListener = async () => {
      try {
        const stopListening =
          await listenForForegroundNotifications();

        if (cancelled) {
          stopListening();
          return;
        }

        unsubscribe = stopListening;
      } catch (error) {
        console.error(
          "Foreground notification listener failed:",
          error
        );
      }
    };


    startListener();


    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [notificationState]);


  const handleLogout = async () => {
    await logout();

    navigate("/login");
  };


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>TaxiLink</h1>

          <small>
            Smart Taxi Demand Monitoring and Dispatch
          </small>
        </div>

        <nav>
          <NavLink to="/dashboard">
            Dashboard
          </NavLink>

          <NavLink to="/routes">
            Routes
          </NavLink>

          {user.role === "DISPATCHER" && (
            <NavLink to="/drivers">
              Drivers
            </NavLink>
          )}

          {user.role === "DRIVER" && (
            <NavLink to="/dispatch">
              Dispatch
            </NavLink>
          )}

          <NavLink to="/profile">
            Profile
          </NavLink>

          <button
            className="link-button"
            onClick={handleLogout}
            type="button"
          >
            Logout
          </button>
        </nav>
      </header>


      <main className="page-container">
        <div className="user-summary">
          Signed in as{" "}

          <strong>
            {user.username}
          </strong>

          {" · "}

          {user.role_display}
        </div>


        {notificationState === "denied" && (
          <div
            className="error-message"
            role="alert"
          >
            Browser notifications are blocked.
            Enable notifications for TaxiLink in
            your browser site settings.
          </div>
        )}


        {notificationState
          === "unavailable" && (
          <div
            className="error-message"
            role="alert"
          >
            Notifications are unavailable on this
            browser or have not been configured.
          </div>
        )}


        {notificationState === "error" && (
          <div
            className="error-message"
            role="alert"
          >
            Notifications could not connect.
            TaxiLink will retry automatically.
          </div>
        )}


        {user.role === "PASSENGER" && (
          <PassengerLocationMonitor />
        )}


        {children}
      </main>
    </div>
  );
}