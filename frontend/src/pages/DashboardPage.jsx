import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { Link } from "react-router-dom";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
import PassengerTaxiTrackingModal from "../components/PassengerTaxiTrackingModal";
import { useAuth } from "../context/AuthContext";


function getLocalDateValue(date) {
  const year = date.getFullYear();

  const month = String(
    date.getMonth() + 1
  ).padStart(2, "0");

  const day = String(
    date.getDate()
  ).padStart(2, "0");

  return `${year}-${month}-${day}`;
}


function extractError(
  error,
  fallbackMessage
) {
  const data = error.response?.data;

  if (!data) {
    return fallbackMessage;
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
    firstValue
    || fallbackMessage
  );
}


function DashboardCard({
  title,
  value,
  description,
  link,
  linkText,
  action,
}) {
  return (
    <article className="dashboard-card">
      <h3>{title}</h3>

      {value !== undefined && (
        <div className="dashboard-value">
          {value}
        </div>
      )}

      {description && (
        <p>{description}</p>
      )}

      {link && (
        <Link
          className="action-button"
          to={link}
          state={{ fromDashboard: true }}
        >
          {linkText}
        </Link>
      )}

      {action}
    </article>
  );
}


export default function DashboardPage() {
  const { user } = useAuth();

  const [
    waitingRequest,
    setWaitingRequest,
  ] = useState(null);

  const [
    passengerDispatch,
    setPassengerDispatch,
  ] = useState(null);

  const [
    availability,
    setAvailability,
  ] = useState(null);

  const [
    assignments,
    setAssignments,
  ] = useState([]);

  const [
    availableDrivers,
    setAvailableDrivers,
  ] = useState([]);

  const [routes, setRoutes] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [
    updatingAvailability,
    setUpdatingAvailability,
  ] = useState(false);

  const [message, setMessage] =
    useState("");

  const [error, setError] =
    useState("");

  const [
    trackingOpen,
    setTrackingOpen,
  ] = useState(false);

  const isPassenger =
    user.role === "PASSENGER";

  const isDriver =
    user.role === "DRIVER";

  const isDispatcher =
    user.role === "DISPATCHER";


  const loadDashboard = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError("");
      }

      try {
        if (isPassenger) {
          const response =
            await api.get(
              "/transport/waiting-requests/current/"
            );

          setWaitingRequest(
            response.data.request
          );

          setPassengerDispatch(
            response.data.dispatch
          );
        }


        if (isDriver) {
          const [
            availabilityResponse,
            assignmentsResponse,
          ] = await Promise.all([
            api.get(
              "/transport/drivers/availability/"
            ),

            api.get(
              "/transport/dispatches/"
            ),
          ]);

          setAvailability(
            availabilityResponse.data
          );

          setAssignments(
            assignmentsResponse.data
          );
        }


        if (isDispatcher) {
          const [
            assignmentsResponse,
            driversResponse,
            routesResponse,
          ] = await Promise.all([
            api.get(
              "/transport/dispatches/"
            ),

            api.get(
              "/transport/drivers/available/"
            ),

            api.get(
              "/transport/routes/"
            ),
          ]);

          setAssignments(
            assignmentsResponse.data
          );

          setAvailableDrivers(
            driversResponse.data
          );

          setRoutes(
            routesResponse.data
          );
        }
      } catch {
        if (!silent) {
          setError(
            "Dashboard information could not be loaded."
          );
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [
      isPassenger,
      isDriver,
      isDispatcher,
    ]
  );


  useEffect(() => {
    loadDashboard();

    const interval =
      window.setInterval(
        () => {
          loadDashboard(true);
        },
        10000
      );

    return () => {
      window.clearInterval(
        interval
      );
    };
  }, [loadDashboard]);


  const activeDriverDispatch = useMemo(
    () =>
      assignments.find(
        (assignment) =>
          [
            "PENDING",
            "ACCEPTED",
            "EN_ROUTE",
          ].includes(
            assignment.status
          )
      ) || null,
    [assignments]
  );


  const todayAssignments = useMemo(
    () => {
      const today =
        getLocalDateValue(
          new Date()
        );

      return assignments.filter(
        (assignment) =>
          assignment.created_at
          && getLocalDateValue(
            new Date(
              assignment.created_at
            )
          ) === today
      );
    },
    [assignments]
  );


  const waitingDemand = useMemo(
    () => {
      let waitingPeople = 0;

      for (const route of routes) {
        for (
          const spot
          of route.waiting_spots || []
        ) {
          waitingPeople += Number(
            spot.active_waiting_count || 0
          );
        }
      }

      return waitingPeople;
    },
    [routes]
  );


  const dispatcherActivity = useMemo(
    () => {
      const activeStatuses = [
        "PENDING",
        "ACCEPTED",
        "EN_ROUTE",
      ];

      return {
        active: assignments.filter(
          (assignment) =>
            activeStatuses.includes(
              assignment.status
            )
        ).length,

        pending: assignments.filter(
          (assignment) =>
            assignment.status
            === "PENDING"
        ).length,

        enRoute: assignments.filter(
          (assignment) =>
            assignment.status
            === "EN_ROUTE"
        ).length,

        completedToday:
          todayAssignments.filter(
            (assignment) =>
              assignment.status
              === "COMPLETED"
          ).length,
      };
    },
    [
      assignments,
      todayAssignments,
    ]
  );


  const toggleAvailability =
    async () => {
      if (
        !availability
        || activeDriverDispatch
      ) {
        return;
      }

      setError("");
      setMessage("");
      setUpdatingAvailability(true);

      try {
        const response =
          await api.patch(
            "/transport/drivers/availability/",
            {
              is_available:
                !availability
                  .is_available,
            }
          );

        setAvailability(
          response.data
        );

        setMessage(
          response.data.is_available
            ? (
              "You are now available "
              + "for dispatch."
            )
            : (
              "You are now unavailable "
              + "for dispatch."
            )
        );
      } catch (requestError) {
        setError(
          extractError(
            requestError,
            "Availability could not be updated."
          )
        );
      } finally {
        setUpdatingAvailability(
          false
        );
      }
    };


  if (loading) {
    return (
      <AppLayout>
        <div className="page-message">
          Loading dashboard...
        </div>
      </AppLayout>
    );
  }


  return (
    <AppLayout>
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


      {isPassenger && (
        <>
          <section className="page-heading">
            <h2>
              Passenger Dashboard
            </h2>

            <p>
              View your active transport
              request and taxi assignment.
            </p>
          </section>


          <section className="dashboard-grid">
            <DashboardCard
              title="Waiting Request"
              value={
                waitingRequest
                  ? waitingRequest.status
                  : "None"
              }
              description={
                waitingRequest
                  ? (
                    `${waitingRequest.waiting_spot_name} · `
                    + `${waitingRequest.route_name}`
                  )
                  : (
                    "You do not currently have "
                    + "an active waiting request."
                  )
              }
              link="/routes"
              linkText={
                waitingRequest
                  ? "View Waiting Spots"
                  : "Find Waiting Spot"
              }
            />


            <DashboardCard
              title="Party Size"
              value={
                waitingRequest
                  ? waitingRequest.party_size
                  : "—"
              }
              description={
                waitingRequest
                  ? (
                    "Passengers included in "
                    + "your current request."
                  )
                  : "No active request."
              }
            />


            <DashboardCard
              title="Boarding Code"
              value={
                waitingRequest
                  ? waitingRequest.boarding_pin
                  : "—"
              }
              description={
                waitingRequest
                  ? (
                    "Give this code to the Driver "
                    + "when boarding."
                  )
                  : "No boarding code available."
              }
            />


            <DashboardCard
              title="Taxi Assignment"
              description={
                passengerDispatch ? (
                  <>
                    <span>
                      {passengerDispatch.message}
                    </span>

                    {passengerDispatch.driver && (
                      <>
                        <br />
                        <br />

                        <strong>
                          Driver:{" "}
                          {
                            passengerDispatch
                              .driver
                              .name
                          }
                        </strong>

                        <br />

                        <span>
                          Number plate:{" "}
                          {
                            passengerDispatch
                              .driver
                              .number_plate
                          }
                        </span>
                      </>
                    )}
                  </>
                ) : (
                  waitingRequest
                    ? (
                      "Your request is waiting "
                      + "for a taxi assignment."
                    )
                    : (
                      "Create a waiting request "
                      + "to request transport."
                    )
                )
              }
              action={
                passengerDispatch?.status
                  === "EN_ROUTE"
                  && passengerDispatch?.id
                  && passengerDispatch?.route_id
                    ? (
                      <button
                        className="action-button"
                        type="button"
                        onClick={() =>
                          setTrackingOpen(true)
                        }
                      >
                        Track Taxi
                      </button>
                    )
                    : null
              }
            />
          </section>
        </>
      )}


      {isDriver && (
        <>
          <section className="page-heading">
            <h2>
              Driver Dashboard
            </h2>

            <p>
              View your availability and
              current dispatch activity.
            </p>
          </section>


          <section className="dashboard-grid">
            <article className="dashboard-card">
              <h3>
                Availability
              </h3>

              <div className="dashboard-value">
                {availability?.is_available
                  ? "Available"
                  : "Unavailable"}
              </div>


              <p>
                {activeDriverDispatch
                  ? (
                    "Your availability is controlled "
                    + "by the active dispatch."
                  )
                  : availability?.is_available
                    ? (
                      "You are available for "
                      + "dispatch assignments."
                    )
                    : (
                      "You are currently unavailable "
                      + "for dispatch assignments."
                    )}
              </p>


              {activeDriverDispatch ? (
                <span className="empty-note">
                  Active dispatch in progress.
                </span>
              ) : (
                <button
                  className={
                    availability?.is_available
                      ? "danger-button"
                      : "action-button"
                  }
                  type="button"
                  disabled={
                    updatingAvailability
                  }
                  onClick={
                    toggleAvailability
                  }
                >
                  {updatingAvailability
                    ? "Updating..."
                    : availability
                        ?.is_available
                      ? "Go Unavailable"
                      : "Go Available"}
                </button>
              )}
            </article>


            <DashboardCard
              title="Current Dispatch"
              value={
                activeDriverDispatch
                  ? (
                    activeDriverDispatch
                      .status_display
                  )
                  : "None"
              }
              description={
                activeDriverDispatch
                  ? (
                    `${activeDriverDispatch.route_name} · `
                    + `${activeDriverDispatch.passenger_count} `
                    + "passenger(s)"
                  )
                  : (
                    "You do not currently have "
                    + "an active assignment."
                  )
              }
              link="/dispatch"
              linkText="Open Dispatch"
            />


            <DashboardCard
              title="Today's Assignments"
              value={
                todayAssignments.length
              }
              description={
                "Dispatch assignments created "
                + "for you today."
              }
              link="/dispatch/history"
              linkText="View History"
            />


            <DashboardCard
              title="Completed Today"
              value={
                todayAssignments.filter(
                  (assignment) =>
                    assignment.status
                    === "COMPLETED"
                ).length
              }
              description={
                "Trips you completed today."
              }
            />
          </section>
        </>
      )}


      {isDispatcher && (
        <>
          <section className="page-heading">
            <h2>
              Dispatcher Dashboard
            </h2>

            <p>
              Monitor current passenger demand,
              Drivers and dispatch activity.
            </p>
          </section>


          <section className="dashboard-grid">
            <DashboardCard
              title="Waiting Demand"
              value={
                waitingDemand
              }
              description={
                "People currently waiting across "
                + "all active waiting spots."
              }
              link="/demand"
              linkText="View Demand"
            />


            <DashboardCard
              title="Available Drivers"
              value={
                availableDrivers.length
              }
              description={
                "Drivers currently available "
                + "for dispatch assignment."
              }
              link="/available-drivers"
              linkText="View Available Drivers"
            />


            <DashboardCard
              title="Active Dispatches"
              value={
                dispatcherActivity.active
              }
              description={
                `${dispatcherActivity.pending} pending · `
                + `${dispatcherActivity.enRoute} en route`
              }
              link="/dispatch/active"
              linkText="View Active Dispatches"
            />


            <DashboardCard
              title="Today's Dispatches"
              value={
                todayAssignments.length
              }
              description={
                `${dispatcherActivity.completedToday} `
                + "completed today."
              }
              link="/dispatch/history"
              linkText="View History"
            />
          </section>
        </>
      )}


      {trackingOpen
        && passengerDispatch?.status
          === "EN_ROUTE"
        && (
          <PassengerTaxiTrackingModal
            dispatch={
              passengerDispatch
            }
            waitingRequest={
              waitingRequest
            }
            onClose={() =>
              setTrackingOpen(false)
            }
          />
        )}
    </AppLayout>
  );
}
