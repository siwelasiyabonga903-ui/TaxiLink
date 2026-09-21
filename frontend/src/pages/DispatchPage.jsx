import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { Navigate } from "react-router-dom";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";


function extractError(error, fallback) {
  const data = error.response?.data;

  if (!data) {
    return fallback;
  }

  const firstValue =
    Object.values(data).flat()[0];

  if (
    typeof firstValue === "object"
    && firstValue !== null
  ) {
    return String(
      Object.values(
        firstValue
      ).flat()[0]
    );
  }

  return String(
    firstValue || fallback
  );
}


export default function DispatchPage() {
  const { user } = useAuth();

  const [assignments, setAssignments] =
    useState([]);

  const [boardingCodes, setBoardingCodes] =
    useState({});

  const [loading, setLoading] =
    useState(true);

  const [message, setMessage] =
    useState("");

  const [error, setError] =
    useState("");

  const [
  locationTrackingState,
  setLocationTrackingState,
  ] = useState("idle");

  const isDriver =
    user.role === "DRIVER";


  const activeAssignments = useMemo(
    () =>
      assignments.filter(
        (assignment) =>
          [
            "PENDING",
            "ACCEPTED",
            "EN_ROUTE",
          ].includes(
            assignment.status
          )
      ),
    [assignments]
  );

  const enRouteAssignmentId =
  useMemo(
    () =>
      activeAssignments.find(
        (assignment) =>
          assignment.status
          === "EN_ROUTE"
      )?.id || null,
    [activeAssignments]
  );

  const loadData = useCallback(
    async (silent = false) => {
      if (!isDriver) {
        if (!silent) {
          setLoading(false);
        }

        return;
      }

      if (!silent) {
        setLoading(true);
      }

      try {
        const response = await api.get(
          "/transport/dispatches/"
        );

        setAssignments(
          response.data
        );
      } catch {
        if (!silent) {
          setError(
            "Current dispatch information could not be loaded."
          );
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [isDriver]
  );


  useEffect(() => {
    loadData();

    const interval =
      window.setInterval(
        () => {
          loadData(true);
        },
        10000
      );

    return () => {
      window.clearInterval(
        interval
      );
    };
  }, [loadData]);

useEffect(() => {
  if (!isDriver || !enRouteAssignmentId) {
    setLocationTrackingState("idle");
    return undefined;
  }

  if (!navigator.geolocation) {
    setLocationTrackingState("unsupported");
    return undefined;
  }

  let stopped = false;
  let watchId = null;
  let lastSentAt = 0;
  let latestPosition = null;
  let retryTimer = null;

  setLocationTrackingState("starting");

  const sendPosition = async (
    position,
    retry = false
  ) => {
    if (stopped) {
      return;
    }

    latestPosition = position;

    const now = Date.now();

    if (
      !retry
      && now - lastSentAt < 5000
    ) {
      return;
    }

    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }

    lastSentAt = now;

    const accuracy =
      Number.isFinite(position.coords.accuracy)
        ? position.coords.accuracy.toFixed(2)
        : null;

    try {
      await api.post(
        `/transport/dispatches/${enRouteAssignmentId}/location/`,
        {
          latitude:
            position.coords.latitude.toFixed(6),
          longitude:
            position.coords.longitude.toFixed(6),
          accuracy_meters: accuracy,
        }
      );

      if (!stopped) {
        setLocationTrackingState("active");
      }
    } catch (requestError) {
      if (stopped) {
        return;
      }

      const responseStatus =
        requestError.response?.status;

      if ([400, 403, 404].includes(responseStatus)) {
        stopped = true;
        setLocationTrackingState("stopped");

        if (watchId !== null) {
          navigator.geolocation.clearWatch(watchId);
        }

        return;
      }

      setLocationTrackingState("error");

      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }

      retryTimer = window.setTimeout(() => {
        retryTimer = null;

        if (!stopped && latestPosition) {
          sendPosition(latestPosition, true);
        }
      }, 5000);
    }
  };

  const handleLocationError = (locationError) => {
    if (stopped) {
      return;
    }

    if (locationError.code === 1) {
      stopped = true;

      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
        retryTimer = null;
      }

      setLocationTrackingState("denied");

      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
      }

      return;
    }

    setLocationTrackingState("error");
  };

  watchId = navigator.geolocation.watchPosition(
    sendPosition,
    handleLocationError,
    {
      enableHighAccuracy: true,
      maximumAge: 5000,
      timeout: 15000,
    }
  );

  return () => {
    stopped = true;

    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }

    if (watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
    }
  };
}, [isDriver, enRouteAssignmentId]);


  const handleBoardingCodeChange = (
    assignmentId,
    waitingSpotId,
    value
  ) => {
    const key =
      `${assignmentId}-${waitingSpotId}`;

    setBoardingCodes(
      (current) => ({
        ...current,

        [key]:
          value.toUpperCase(),
      })
    );
  };


  const respondToDispatch = async (
    assignmentId,
    response
  ) => {
    setError("");
    setMessage("");

    try {
      await api.post(
        `/transport/dispatches/${assignmentId}/${response}/`
      );

      setMessage(
        response === "accept"
          ? (
            "Trip accepted. "
            + "You are now en route."
          )
          : "Dispatch rejected."
      );

      await loadData(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "The dispatch response could not be saved."
        )
      );
    }
  };


  const updateTripStatus = async (
    assignmentId,
    action,
    successMessage
  ) => {
    setError("");
    setMessage("");

    try {
      await api.post(
        `/transport/dispatches/${assignmentId}/${action}/`
      );

      setMessage(
        successMessage
      );

      await loadData(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Trip status could not be updated."
        )
      );
    }
  };


  const confirmBoarding = async (
    assignmentId,
    spot
  ) => {
    const key =
      `${assignmentId}-${spot.id}`;

    const boardingCode = (
      boardingCodes[key] || ""
    )
      .trim()
      .toUpperCase();

    setError("");
    setMessage("");

    if (!boardingCode) {
      setError(
        "Enter the passenger boarding code."
      );

      return;
    }

    try {
      await api.post(
        `/transport/dispatches/${assignmentId}/confirm-boarding/`,
        {
          waiting_spot:
            spot.id,

          boarding_pin:
            boardingCode,
        }
      );

      setBoardingCodes(
        (current) => {
          const updated = {
            ...current,
          };

          delete updated[key];

          return updated;
        }
      );

      setMessage(
        `Passenger group boarded at ${spot.name}.`
      );

      await loadData(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Boarding could not be confirmed."
        )
      );
    }
  };


  if (!isDriver) {
    return (
      <Navigate
        to={
          user.role === "DISPATCHER"
            ? "/dispatch/active"
            : "/dashboard"
        }
        replace
      />
    );
  }


  return (
    <AppLayout>
      <section className="page-heading">
        <h2>
          Current Dispatch
        </h2>

        <p>
          Your current taxi assignment and
          trip controls.
        </p>
      </section>


      {message && (
        <div className="success-message">
          {message}
        </div>
      )}


      {error && (
        <div className="error-message">
          {error}
        </div>
      )}


      <section className="dispatch-list">
        <h3>
          Current Assignment
        </h3>


        {loading && (
          <div className="page-message">
            Loading current dispatch...
          </div>
        )}


        {!loading
          && activeAssignments.length
            === 0 && (
            <div className="route-card">
              No current dispatch assignment.
            </div>
          )}


        {!loading
          && activeAssignments.map(
            (assignment) => (
              <article
                className="dispatch-card"
                key={assignment.id}
              >
                <div>
                  <div className="dispatch-title-row">
                    <h4>
                      {
                        assignment
                          .route_name
                      }
                    </h4>

                    <span
                      className={
                        `dispatch-status ${
                          assignment.status
                            .toLowerCase()
                        }`
                      }
                    >
                      {
                        assignment
                          .status_display
                      }
                    </span>
                  </div>


                  <p>
                    Route:{" "}
                    {
                      assignment
                        .route_name
                    }
                  </p>


                  <p>
                    Passengers assigned:{" "}

                    <strong>
                      {
                        assignment
                          .passenger_count
                      }
                    </strong>
                  </p>


                  {assignment.notes && (
                    <p>
                      Notes:{" "}
                      {
                        assignment
                          .notes
                      }
                    </p>
                  )}


                  <small>
                    Assigned:{" "}

                    {new Date(
                      assignment.created_at
                    ).toLocaleString()}
                  </small>
                </div>


                {assignment.status
                  === "PENDING" && (
                  <div className="dispatch-actions">
                    <button
                      className="action-button"
                      type="button"
                      onClick={() =>
                        respondToDispatch(
                          assignment.id,
                          "accept"
                        )
                      }
                    >
                      Accept
                    </button>

                    <button
                      className="danger-button"
                      type="button"
                      onClick={() =>
                        respondToDispatch(
                          assignment.id,
                          "reject"
                        )
                      }
                    >
                      Reject
                    </button>
                  </div>
                )}


                {assignment.status
                  === "EN_ROUTE" && (
                  <>

                    {locationTrackingState
                        === "starting" && (
                        <p className="empty-note">
                          Starting live location
                          sharing...
                        </p>
                      )}

                      {locationTrackingState
                        === "active" && (
                        <p className="empty-note">
                          Live taxi location is being
                          shared with your assigned
                          passengers.
                        </p>
                      )}

                      {locationTrackingState
                        === "denied" && (
                        <div className="error-message">
                          Location permission is required
                          for live taxi tracking.
                        </div>
                      )}

                      {locationTrackingState
                        === "unsupported" && (
                        <div className="error-message">
                          Live location is not supported
                          by this browser.
                        </div>
                      )}

                      {locationTrackingState
                        === "error" && (
                        <div className="error-message">
                          TaxiLink could not send your
                          live location. Location sharing
                          will retry when a new position
                          is received.
                        </div>
                      )}
                    <div className="dispatch-pickups">
                      <h4>
                        Pickup Spots
                      </h4>


                      {assignment
                        .pickup_spots
                        ?.map(
                          (spot) => {
                            const key =
                              `${assignment.id}-${spot.id}`;

                            return (
                              <div
                                className="route-card"
                                key={spot.id}
                              >
                                <h4>
                                  {spot.name}
                                </h4>


                                <p>
                                  Assigned:{" "}

                                  <strong>
                                    {
                                      spot
                                        .assigned_count
                                    }
                                  </strong>
                                </p>


                                <p>
                                  Boarded:{" "}

                                  <strong>
                                    {
                                      spot
                                        .boarded_count
                                    }
                                  </strong>
                                </p>


                                <p>
                                  Still waiting:{" "}

                                  <strong>
                                    {
                                      spot
                                        .waiting_count
                                    }
                                  </strong>
                                </p>


                                {spot
                                  .waiting_count
                                  > 0 && (
                                  <div className="dispatch-actions">
                                    <input
                                      type="text"
                                      maxLength="3"
                                      placeholder="A21"
                                      value={
                                        boardingCodes[
                                          key
                                        ] || ""
                                      }
                                      onChange={(
                                        event
                                      ) =>
                                        handleBoardingCodeChange(
                                          assignment.id,
                                          spot.id,
                                          event
                                            .target
                                            .value
                                        )
                                      }
                                      onKeyDown={(
                                        event
                                      ) => {
                                        if (
                                          event
                                            .key
                                          === "Enter"
                                        ) {
                                          event
                                            .preventDefault();

                                          confirmBoarding(
                                            assignment.id,
                                            spot
                                          );
                                        }
                                      }}
                                    />

                                    <button
                                      className="action-button"
                                      type="button"
                                      onClick={() =>
                                        confirmBoarding(
                                          assignment.id,
                                          spot
                                        )
                                      }
                                    >
                                      Confirm Boarding
                                    </button>
                                  </div>
                                )}


                                {spot
                                  .waiting_count
                                  === 0 && (
                                  <p className="empty-note">
                                    No linked passengers
                                    are currently waiting
                                    here.
                                  </p>
                                )}
                              </div>
                            );
                          }
                        )}
                    </div>


                    <div className="dispatch-actions">
                      <button
                        className="action-button"
                        type="button"
                        onClick={() =>
                          updateTripStatus(
                            assignment.id,
                            "complete",
                            "Trip completed successfully."
                          )
                        }
                      >
                        Complete Trip
                      </button>
                    </div>
                  </>
                )}
              </article>
            )
          )}
      </section>
    </AppLayout>
  );
}