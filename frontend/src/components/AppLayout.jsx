import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  NavLink,
  useLocation,
  useNavigate,
} from "react-router-dom";

import PassengerLocationMonitor
  from "./PassengerLocationMonitor";

import { useAuth } from "../context/AuthContext";

import {
  listenForForegroundNotifications,
  registerPushNotifications,
} from "../notifications";

import NotificationCenter from "./NotificationCenter";

const NOTIFICATION_RETRY_DELAY_MS = 15000;


export default function AppLayout({
  children,
}) {
  const { user, logout } = useAuth();

  const navigate = useNavigate();
  const location = useLocation();
  const menuButtonRef = useRef(null);
  const sidebarRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);

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
  }, [user.id]);


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

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const closeOnWideScreen = () => {
      if (window.innerWidth > 900) setMenuOpen(false);
    };
    window.addEventListener("resize", closeOnWideScreen);
    return () => window.removeEventListener("resize", closeOnWideScreen);
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const priorOverflow = document.body.style.overflow;
    const trigger = menuButtonRef.current;
    document.body.style.overflow = "hidden";
    sidebarRef.current?.querySelector(".sidebar-close")?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
      }
      if (event.key !== "Tab") return;
      const controls = sidebarRef.current?.querySelectorAll(
        "a[href], button:not([disabled])"
      );
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = priorOverflow;
      document.removeEventListener("keydown", onKeyDown);
      if (trigger?.isConnected) trigger.focus();
    };
  }, [menuOpen]);


  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();

    navigate("/login");
  };

  const handleBack = () => {
    if (Number(window.history.state?.idx) > 0) {
      navigate(-1);
    } else if (window.location.pathname !== "/dashboard") {
      navigate("/dashboard", { replace: true });
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        {menuOpen && (
          <button
            className="sidebar-scrim"
            type="button"
            tabIndex={-1}
            aria-label="Close navigation overlay"
            onClick={() => setMenuOpen(false)}
          />
        )}
        <button
          ref={menuButtonRef}
          className="sidebar-toggle"
          type="button"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          aria-controls="main-navigation"
          inert={menuOpen || undefined}
          onClick={() => setMenuOpen(true)}
        >
          ☰
        </button>
        <div className="topbar-heading" inert={menuOpen || undefined}>

          <div>
            <h1>TaxiLink</h1>
            <small>
              Smart Taxi Demand Monitoring and Dispatch
            </small>
          </div>
        </div>

        <div
          className="topbar-notifications"
          inert={menuOpen || undefined}
        >
          <NotificationCenter
            pushState={notificationState}
          />
        </div>

        <nav
          ref={sidebarRef}
          id="main-navigation"
          className={`sidebar-nav${menuOpen ? " is-open" : ""}`}
          aria-label="Main navigation"
          role={menuOpen ? "dialog" : undefined}
          aria-modal={menuOpen || undefined}
          onClick={(event) => {
            if (event.target.closest?.("a")) setMenuOpen(false);
          }}
        >
          <div className="sidebar-brand">
            <strong>TaxiLink</strong>
            <button
              type="button"
              className="sidebar-close"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
            >
              ×
            </button>
          </div>
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


      <main className="page-container" inert={menuOpen || undefined}>
        <div className="user-summary">
          Signed in as{" "}

          <strong>
            {
              [
                user.first_name,
                user.last_name,
              ]
                .filter(Boolean)
                .join(" ")
              || user.email
            }
          </strong>

          {" · "}

          {user.role_display}
        </div>

        {location.state?.fromDashboard === true
          && location.pathname !== "/dashboard" && (
          <div className="dashboard-return-row">
            <button
              className="dashboard-return"
              type="button"
              onClick={() => navigate("/dashboard")}
            >
              <span aria-hidden="true">←</span>
              Back to dashboard
            </button>
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