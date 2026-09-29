import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import api from "../api/client";


const POLL_INTERVAL_MS = 10000;


function formatNotificationTime(value) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat(
    undefined,
    {
      dateStyle: "medium",
      timeStyle: "short",
    }
  ).format(date);
}


function pushStatusMessage(pushState) {
  if (pushState === "denied") {
    return (
      "Device alerts are blocked. "
      + "In-app notifications are still active."
    );
  }

  if (pushState === "unavailable") {
    return (
      "Device alerts are unavailable here. "
      + "In-app notifications are still active."
    );
  }

  if (pushState === "error") {
    return (
      "Device alerts will retry automatically. "
      + "In-app notifications are active."
    );
  }

  return "";
}


export default function NotificationCenter({
  pushState = "idle",
}) {
  const [notifications, setNotifications] =
    useState([]);

  const [open, setOpen] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [loadFailed, setLoadFailed] =
    useState(false);

  const [markingAll, setMarkingAll] =
    useState(false);

  const containerRef = useRef(null);
  const triggerRef = useRef(null);
  const mountedRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const readOverridesRef = useRef(new Set());


  const closePanel = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);


  const loadNotifications = useCallback(
    async (initial = false) => {
      if (requestInFlightRef.current) {
        return;
      }

      requestInFlightRef.current = true;

      if (initial) {
        setLoading(true);
      }

      try {
        const response = await api.get(
          "/transport/notifications/"
        );

        if (!mountedRef.current) {
          return;
        }

        const incomingNotifications =
          Array.isArray(response.data)
            ? response.data
            : [];

        const mergedNotifications =
          incomingNotifications.map(
            (notification) => {
              if (notification.is_read) {
                readOverridesRef.current.delete(
                  notification.id
                );

                return notification;
              }

              if (
                readOverridesRef.current.has(
                  notification.id
                )
              ) {
                return {
                  ...notification,
                  is_read: true,
                };
              }

              return notification;
            }
          );

        setNotifications(
          mergedNotifications
        );

        setLoadFailed(false);
      } catch {
        if (mountedRef.current) {
          setLoadFailed(true);
        }
      } finally {
        requestInFlightRef.current = false;

        if (mountedRef.current && initial) {
          setLoading(false);
        }
      }
    },
    []
  );


  useEffect(() => {
    mountedRef.current = true;

    loadNotifications(true);

    const interval = window.setInterval(
      () => {
        if (
          document.visibilityState === "visible"
        ) {
          loadNotifications();
        }
      },
      POLL_INTERVAL_MS
    );

    const refreshWhenVisible = () => {
      if (
        document.visibilityState === "visible"
      ) {
        loadNotifications();
      }
    };

    const refreshOnFocus = () => {
      loadNotifications();
    };

    document.addEventListener(
      "visibilitychange",
      refreshWhenVisible
    );

    window.addEventListener(
      "focus",
      refreshOnFocus
    );

    return () => {
      mountedRef.current = false;

      window.clearInterval(interval);

      document.removeEventListener(
        "visibilitychange",
        refreshWhenVisible
      );

      window.removeEventListener(
        "focus",
        refreshOnFocus
      );
    };
  }, [loadNotifications]);


  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const closeOnOutsideClick = (event) => {
      if (
        !containerRef.current?.contains(
          event.target
        )
      ) {
        setOpen(false);
      }
    };

    const closeOnEscape = (event) => {
      if (event.key === "Escape") {
        closePanel();
      }
    };

    document.addEventListener(
      "pointerdown",
      closeOnOutsideClick
    );

    document.addEventListener(
      "keydown",
      closeOnEscape
    );

    return () => {
      document.removeEventListener(
        "pointerdown",
        closeOnOutsideClick
      );

      document.removeEventListener(
        "keydown",
        closeOnEscape
      );
    };
  }, [
    open,
    closePanel,
  ]);


  const markRead = async (notification) => {
    if (notification.is_read) {
      return;
    }

    readOverridesRef.current.add(
      notification.id
    );

    setNotifications(
      (current) =>
        current.map(
          (item) =>
            item.id === notification.id
              ? {
                  ...item,
                  is_read: true,
                }
              : item
        )
    );

    try {
      await api.post(
        `/transport/notifications/${notification.id}/read/`
      );
    } catch {
      readOverridesRef.current.delete(
        notification.id
      );

      setNotifications(
        (current) =>
          current.map(
            (item) =>
              item.id === notification.id
                ? {
                    ...item,
                    is_read: false,
                  }
                : item
          )
      );

      setLoadFailed(true);
    }
  };


  const markAllRead = async () => {
    const unreadIds = new Set(
      notifications
        .filter((item) => !item.is_read)
        .map((item) => item.id)
    );

    if (unreadIds.size === 0) {
      return;
    }

    unreadIds.forEach((notificationId) => {
      readOverridesRef.current.add(
        notificationId
      );
    });

    setMarkingAll(true);

    setNotifications(
      (current) =>
        current.map(
          (item) => ({
            ...item,
            is_read: true,
          })
        )
    );

    try {
      await api.post(
        "/transport/notifications/read-all/"
      );

      setLoadFailed(false);
    } catch {
      unreadIds.forEach((notificationId) => {
        readOverridesRef.current.delete(
          notificationId
        );
      });

      setNotifications(
        (current) =>
          current.map(
            (item) =>
              unreadIds.has(item.id)
                ? {
                    ...item,
                    is_read: false,
                  }
                : item
          )
      );

      setLoadFailed(true);
    } finally {
      setMarkingAll(false);
    }
  };


  const unreadCount = notifications.filter(
    (notification) => !notification.is_read
  ).length;

  const deviceMessage =
    pushStatusMessage(pushState);


  return (
    <div
      className="notification-center"
      ref={containerRef}
    >
      <button
        ref={triggerRef}
        className="notification-bell"
        type="button"
        aria-label={
          unreadCount > 0
            ? `${unreadCount} unread notifications`
            : "Notifications"
        }
        aria-expanded={open}
        aria-controls="notification-panel"
        onClick={() => {
          setOpen((current) => !current);

          if (!open) {
            loadNotifications();
          }
        }}
      >
        <span aria-hidden="true">🔔</span>

        {unreadCount > 0 && (
          <span className="notification-badge">
            {unreadCount > 99
              ? "99+"
              : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <section
          className="notification-panel"
          id="notification-panel"
          aria-label="TaxiLink notifications"
        >
          <header className="notification-panel-header">
            <div>
              <strong>
                Notifications
              </strong>

              <small>
                {unreadCount === 0
                  ? "No unread notifications"
                  : `${unreadCount} unread`}
              </small>
            </div>

            <div className="notification-header-actions">
              {unreadCount > 0 && (
                <button
                  className="notification-mark-all"
                  type="button"
                  disabled={markingAll}
                  onClick={markAllRead}
                >
                  {markingAll
                    ? "Marking..."
                    : "Mark all read"}
                </button>
              )}

              <button
                className="notification-close"
                type="button"
                aria-label="Close notifications"
                onClick={closePanel}
              >
                <span aria-hidden="true">
                  ×
                </span>
              </button>
            </div>
          </header>

          {deviceMessage && (
            <p className="notification-device-note">
              {deviceMessage}
            </p>
          )}

          {loading && (
            <p className="notification-empty">
              Loading notifications...
            </p>
          )}

          {!loading
            && !loadFailed
            && notifications.length === 0 && (
            <p className="notification-empty">
              You have no notifications yet.
            </p>
          )}

          {notifications.length > 0 && (
            <div className="notification-list">
              {notifications.map(
                (notification) => (
                  <button
                    className={
                      `notification-item${
                        notification.is_read
                          ? " is-read"
                          : " is-unread"
                      }`
                    }
                    type="button"
                    key={notification.id}
                    onClick={() =>
                      markRead(notification)
                    }
                  >
                    <span className="notification-item-title">
                      {notification.title}
                    </span>

                    <span className="notification-item-message">
                      {notification.message}
                    </span>

                    <time
                      dateTime={
                        notification.created_at
                      }
                    >
                      {formatNotificationTime(
                        notification.created_at
                      )}
                    </time>
                  </button>
                )
              )}
            </div>
          )}

          {loadFailed && (
            <p
              className="notification-refresh-error"
              role="status"
            >
              {notifications.length > 0
                ? (
                  "Notifications could not be refreshed. "
                  + "Showing the latest available information."
                )
                : (
                  "Notifications could not be loaded. "
                  + "TaxiLink will try again automatically."
                )}
            </p>
          )}
        </section>
      )}
    </div>
  );
}