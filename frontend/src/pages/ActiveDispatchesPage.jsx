import {
  Navigate,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

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

  return String(
    firstValue || fallback
  );
}


export default function ActiveDispatchesPage() {
  const { user } = useAuth();

  const [assignments, setAssignments] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [message, setMessage] =
    useState("");

  const [error, setError] =
    useState("");


  const loadDispatches = useCallback(
    async (silent = false) => {
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
        setError(
          "Active dispatches could not be loaded."
        );
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    []
  );


  useEffect(() => {
    loadDispatches();

    const interval = window.setInterval(
      () => {
        loadDispatches(true);
      },
      10000
    );

    return () => {
      window.clearInterval(interval);
    };
  }, [loadDispatches]);


  const activeDispatches = useMemo(
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


  const cancelDispatch = async (
    assignmentId
  ) => {
    const confirmed = window.confirm(
      "Cancel this dispatch assignment? "
      + "The driver will become available again "
      + "and the passengers will remain waiting."
    );

    if (!confirmed) {
      return;
    }

    setError("");
    setMessage("");

    try {
      await api.post(
        `/transport/dispatches/${assignmentId}/cancel/`
      );

      setMessage(
        "Dispatch cancelled successfully."
      );

      await loadDispatches(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "The dispatch could not be cancelled."
        )
      );
    }
  };


  if (user.role !== "DISPATCHER") {
    return (
      <Navigate
        to="/dashboard"
        replace
      />
    );
  }


  return (
    <AppLayout>
      <section className="page-heading">
        <h2>Active Dispatches</h2>

        <p>
          Current taxi assignments that are
          waiting for a Driver response or
          already en route.
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

      {loading ? (
        <div className="page-message">
          Loading active dispatches...
        </div>
      ) : activeDispatches.length === 0 ? (
        <div className="route-card">
          There are no active dispatches.
        </div>
      ) : (
        <section className="dispatch-list">
          {activeDispatches.map(
            (assignment) => (
              <article
                className="dispatch-card"
                key={assignment.id}
              >
                <div>
                  <div className="dispatch-title-row">
                    <h3>
                      {assignment.route_name}
                    </h3>

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
                    Driver:{" "}
                    <strong>
                      {assignment.driver_name}
                    </strong>
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
                      {assignment.notes}
                    </p>
                  )}

                  <small>
                    Dispatched:{" "}
                    {new Date(
                      assignment.created_at
                    ).toLocaleString()}
                  </small>
                </div>

                <div className="dispatch-actions">
                  <button
                    className="danger-button"
                    type="button"
                    onClick={() =>
                      cancelDispatch(
                        assignment.id
                      )
                    }
                  >
                    Cancel Dispatch
                  </button>
                </div>
              </article>
            )
          )}
        </section>
      )}
    </AppLayout>
  );
}