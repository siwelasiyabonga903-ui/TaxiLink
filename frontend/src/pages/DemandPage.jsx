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

  return String(firstValue || fallback);
}


export default function DemandPage() {
  const { user } = useAuth();

  const [routes, setRoutes] = useState([]);

  const [
    availableDrivers,
    setAvailableDrivers,
  ] = useState([]);

  const [selectedRoute, setSelectedRoute] =
    useState(null);

  const [selectedDriver, setSelectedDriver] =
    useState("");

  const [loading, setLoading] =
    useState(true);

  const [dispatching, setDispatching] =
    useState(false);

  const [error, setError] =
    useState("");

  const [message, setMessage] =
    useState("");


  const loadDemand = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError("");
      }

      try {
        const [
          routesResponse,
          driversResponse,
        ] = await Promise.all([
          api.get(
            "/transport/routes/"
          ),
          api.get(
            "/transport/drivers/available/"
          ),
        ]);

        setRoutes(
          routesResponse.data
        );

        setAvailableDrivers(
          driversResponse.data
        );
      } catch {
        if (!silent) {
          setError(
            "Waiting demand could not be loaded."
          );
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    []
  );


  useEffect(() => {
    loadDemand();

    const interval =
      window.setInterval(
        () => {
          loadDemand(true);
        },
        10000
      );

    return () => {
      window.clearInterval(interval);
    };
  }, [loadDemand]);

  useEffect(() => {
    if (selectedRoute) {
        document.body.style.overflow = "hidden";
    } else {
        document.body.style.overflow = "";
    }

    return () => {
        document.body.style.overflow = "";
    };
    }, [selectedRoute]);

  const routesWithDemand = useMemo(
    () =>
      routes
        .map((route) => {
          const waitingSpots = (
            route.waiting_spots || []
          ).filter(
            (spot) =>
              spot.is_active
              && spot.active_waiting_count > 0
          );

          const totalWaiting =
            waitingSpots.reduce(
              (total, spot) =>
                total
                + spot.active_waiting_count,
              0
            );

          return {
            ...route,
            waitingSpots,
            totalWaiting,
          };
        })
        .filter(
          (route) =>
            route.is_active
            && route.totalWaiting > 0
        ),
    [routes]
  );


  const totalWaiting = useMemo(
    () =>
      routesWithDemand.reduce(
        (total, route) =>
          total + route.totalWaiting,
        0
      ),
    [routesWithDemand]
  );


  const openDispatchModal = (route) => {
    setSelectedRoute(route);
    setSelectedDriver("");
    setError("");
    setMessage("");
  };


  const closeDispatchModal = () => {
    if (dispatching) {
      return;
    }

    setSelectedRoute(null);
    setSelectedDriver("");
  };


  const dispatchDriver = async (event) => {
    event.preventDefault();

    if (
      !selectedRoute
      || !selectedDriver
    ) {
      return;
    }

    setError("");
    setMessage("");
    setDispatching(true);

    try {
      await api.post(
        "/transport/dispatches/",
        {
          driver: Number(
            selectedDriver
          ),
          route: selectedRoute.id,
          notes: "",
        }
      );

      const routeName =
        selectedRoute.name;

      setSelectedRoute(null);
      setSelectedDriver("");

      setMessage(
        `Driver dispatched successfully to ${routeName}.`
      );

      await loadDemand(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "The driver could not be dispatched."
        )
      );
    } finally {
      setDispatching(false);
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
        <h2>Waiting Demand</h2>

        <p>
          Current passenger demand arranged
          by route and waiting spot.
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
          Loading waiting demand...
        </div>
      ) : (
        <>
          <section className="availability-card">
            <div>
              <h3>
                Total People Waiting
              </h3>

              <strong>
                {totalWaiting}
              </strong>
            </div>
          </section>


          {routesWithDemand.length === 0 ? (
            <div className="route-card">
              No passengers are currently
              waiting.
            </div>
          ) : (
            <section className="dispatch-list">
              {routesWithDemand.map(
                (route) => (
                  <article
                    className="dispatch-card"
                    key={route.id}
                  >
                    <div>
                      <h3>
                        {route.name}
                      </h3>

                      <p>
                        {route.origin}
                        {" → "}
                        {route.destination}
                      </p>
                    </div>


                    <div className="dispatch-pickups">
                      {route.waitingSpots.map(
                        (spot) => (
                          <div
                            className="route-card"
                            key={spot.id}
                          >
                            <h4>
                              {spot.name}
                            </h4>

                            <p>
                              <strong>
                                {
                                  spot
                                    .active_waiting_count
                                }
                              </strong>

                              {" "}

                              {spot
                                .active_waiting_count
                                === 1
                                ? "person"
                                : "people"}

                              {" "}waiting
                            </p>
                          </div>
                        )
                      )}
                    </div>


                    <p>
                      Route total:{" "}

                      <strong>
                        {route.totalWaiting}
                      </strong>

                      {" "}

                      {route.totalWaiting === 1
                        ? "person"
                        : "people"}

                      {" "}waiting
                    </p>


                    <div className="dispatch-actions">
                      <button
                        className="action-button"
                        type="button"
                        onClick={() =>
                          openDispatchModal(
                            route
                          )
                        }
                      >
                        Dispatch Driver
                      </button>
                    </div>
                  </article>
                )
              )}
            </section>
          )}
        </>
      )}


      {selectedRoute && (
        <div
          className="modal-backdrop"
          onMouseDown={
            closeDispatchModal
          }
        >
          <section
            className="dispatch-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Dispatch Driver
            </h3>

            <p>
              <strong>
                {selectedRoute.name}
              </strong>
            </p>

            <p>
              {selectedRoute.totalWaiting}
              {" "}

              {selectedRoute.totalWaiting === 1
                ? "person"
                : "people"}

              {" "}currently waiting.
            </p>


            <form
              onSubmit={dispatchDriver}
            >
              <label>
                Select Available Driver

                <select
                  value={selectedDriver}
                  onChange={(event) =>
                    setSelectedDriver(
                      event.target.value
                    )
                  }
                  required
                >
                  <option value="">
                    Select Driver
                  </option>

                  {availableDrivers.map(
                    (driver) => (
                      <option
                        key={driver.id}
                        value={driver.id}
                      >
                        {driver.full_name}
                        {" — "}
                        {driver.number_plate}
                      </option>
                    )
                  )}
                </select>
              </label>


              {availableDrivers.length === 0 && (
                <p className="empty-note">
                  No drivers are currently
                  available.
                </p>
              )}


              <div className="dispatch-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={dispatching}
                  onClick={
                    closeDispatchModal
                  }
                >
                  Cancel
                </button>

                <button
                  className="action-button"
                  type="submit"
                  disabled={
                    dispatching
                    || !selectedDriver
                  }
                >
                  {dispatching
                    ? "Dispatching..."
                    : "Dispatch"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </AppLayout>
  );
}