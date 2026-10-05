import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import api from "../api/client";


function getBrowserLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(
        new Error(
          "Location services are not supported by this browser."
        )
      );

      return;
    }

    navigator.geolocation.getCurrentPosition(
      resolve,
      reject,
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      }
    );
  });
}


export default function PassengerLocationMonitor() {
  const [monitorMessage, setMonitorMessage] =
    useState("");

  const checkingRef =
    useRef(false);

  const [graceDeadline, setGraceDeadline] =
    useState(null);

  const [remainingSeconds, setRemainingSeconds] =
    useState(0);


  const revalidateLocation = useCallback(
    async () => {
      if (checkingRef.current) {
        return;
      }

      checkingRef.current = true;

      try {
        const currentResponse =
          await api.get(
            "/transport/waiting-requests/current/"
          );

        const waitingRequest =
          currentResponse.data.request;


        if (
          !waitingRequest
          || waitingRequest.status
            !== "WAITING"
        ) {
          setGraceDeadline(null);
          setRemainingSeconds(0);

          return;
        }


        let position;

        try {
          position =
            await getBrowserLocation();
        } catch {
          setMonitorMessage(
            "TaxiLink cannot verify your location while you are waiting. "
            + "Please allow location access."
          );

          return;
        }


        const response =
          await api.post(
            "/transport/waiting-requests/revalidate-location/",
            {
              latitude:
                position.coords.latitude
                  .toFixed(6),

              longitude:
                position.coords.longitude
                  .toFixed(6),
            }
          );


        if (response.data.cancelled) {
          setGraceDeadline(null);
          setRemainingSeconds(0);

          setMonitorMessage(
            response.data.detail
            || (
              "Your waiting request was cancelled "
              + "because you left the waiting spot."
            )
          );

          return;
        }


        if (
          response.data
            .grace_period_active
        ) {
          const seconds =
            response.data.grace_seconds_remaining;

          if (
            typeof seconds === "number"
            && Number.isFinite(seconds)
            && seconds >= 0
          ) {
            setGraceDeadline(
              Date.now() + seconds * 1000
            );

            setRemainingSeconds(
              Math.ceil(seconds)
            );

            setMonitorMessage("");
          } else {
            setGraceDeadline(null);
            setRemainingSeconds(0);

            setMonitorMessage(
              "You appear to be outside the waiting spot. "
              + "Return to keep your waiting request active."
            );
          }

          return;
        }


        setGraceDeadline(null);
        setRemainingSeconds(0);
        setMonitorMessage("");
      } catch {
        setMonitorMessage(
          "TaxiLink could not verify your waiting location."
        );
      } finally {
        checkingRef.current = false;
      }
    },
    []
  );


  useEffect(() => {
    revalidateLocation();

    const interval = window.setInterval(
      revalidateLocation,
      10000
    );

    const recheckWhenVisible = () => {
      if (document.visibilityState === "visible") {
        revalidateLocation();
      }
    };

    document.addEventListener(
      "visibilitychange",
      recheckWhenVisible
    );

    const resumeEvents = [
      "focus",
      "pageshow",
      "online",
    ];

    for (const eventName of resumeEvents) {
      window.addEventListener(
        eventName,
        recheckWhenVisible
      );
    }

    return () => {
      window.clearInterval(interval);

      document.removeEventListener(
        "visibilitychange",
        recheckWhenVisible
      );

      for (const eventName of resumeEvents) {
        window.removeEventListener(
          eventName,
          recheckWhenVisible
        );
      }
    };
  }, [revalidateLocation]);


  useEffect(() => {
    if (graceDeadline === null) {
      return;
    }

    const updateCountdown = () => {
      setRemainingSeconds(
        Math.max(
          0,
          Math.ceil(
            (graceDeadline - Date.now()) / 1000
          )
        )
      );
    };

    updateCountdown();

    const timer = window.setInterval(
      updateCountdown,
      1000
    );

    return () => {
      window.clearInterval(timer);
    };
  }, [graceDeadline]);


  const countdownMessage =
    graceDeadline === null
      ? ""
      : remainingSeconds > 0
        ? (
            "You appear to be outside the waiting spot. "
            + `Return within ${remainingSeconds} seconds to keep `
            + "your waiting request active."
          )
        : (
            "The return period has ended. "
            + "Waiting for location verification."
          );

  if (!monitorMessage && !countdownMessage) {
    return null;
  }


  return (
    <>
      {monitorMessage && (
        <div className="error-message">
          {monitorMessage}
        </div>
      )}

      {countdownMessage && (
        <div className="error-message">
          {countdownMessage}
        </div>
      )}
    </>
  );
}