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
        maximumAge: 5000,
      }
    );
  });
}


export default function PassengerLocationMonitor() {
  const [monitorMessage, setMonitorMessage] =
    useState("");

  const checkingRef =
    useRef(false);


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
          setMonitorMessage(
            "You appear to be outside the waiting spot. "
            + "Return within 30 seconds to keep "
            + "your waiting request active."
          );

          return;
        }


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

    const interval =
      window.setInterval(
        () => {
          revalidateLocation();
        },
        10000
      );

    return () => {
      window.clearInterval(
        interval
      );
    };
  }, [revalidateLocation]);


  if (!monitorMessage) {
    return null;
  }


  return (
    <div className="error-message">
      {monitorMessage}
    </div>
  );
}