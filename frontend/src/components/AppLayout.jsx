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


  const handleEnableNotifications = async () => {
    setNotificationState("loading");

    try {
      const result =
        await registerPushNotifications();

      if (result.registered) {
        setNotificationState("enabled");
        return;
      }

      if (
        result.reason === "permission-denied"
      ) {
        setNotificationState("denied");
        return;
      }

      setNotificationState("unavailable");
    } catch (error) {
      console.error(
        "Notification registration failed:",
        error
      );

      setNotificationState("error");
    }
  };


  const notificationButtonText = {
    idle: "Enable notifications",
    loading: "Enabling...",
    enabled: "Notifications enabled",
    denied: "Notifications denied",
    unavailable: "Notifications unavailable",
    error: "Retry notifications",
  }[notificationState];


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
            onClick={
              handleEnableNotifications
            }
            disabled={
              notificationState === "loading"
              || notificationState === "enabled"
            }
            type="button"
          >
            {notificationButtonText}
          </button>

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


        {user.role === "PASSENGER" && (
          <PassengerLocationMonitor />
        )}


        {children}
      </main>
    </div>
  );
}