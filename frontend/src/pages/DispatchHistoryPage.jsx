import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
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


export default function DispatchHistoryPage() {
  const { user } = useAuth();

  const [assignments, setAssignments] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [filterMode, setFilterMode] =
    useState("today");

  const [selectedDate, setSelectedDate] =
    useState(
      getLocalDateValue(new Date())
    );


  const loadHistory = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
      }

      setError("");

      try {
        const response = await api.get(
          "/transport/dispatches/"
        );

        setAssignments(
          response.data
        );
      } catch {
        setError(
          "Dispatch history could not be loaded."
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
    loadHistory();

    const interval = window.setInterval(
      () => {
        loadHistory(true);
      },
      10000
    );

    return () => {
      window.clearInterval(interval);
    };
  }, [loadHistory]);


  const historyAssignments = useMemo(
    () =>
      assignments.filter(
        (assignment) =>
          [
            "COMPLETED",
            "REJECTED",
            "CANCELLED",
          ].includes(
            assignment.status
          )
      ),
    [assignments]
  );


  const filteredHistory = useMemo(
    () => {
      if (filterMode === "all") {
        return historyAssignments;
      }

      const targetDate =
        filterMode === "today"
          ? getLocalDateValue(new Date())
          : selectedDate;

      return historyAssignments.filter(
        (assignment) => {
          if (!assignment.created_at) {
            return false;
          }

          return (
            getLocalDateValue(
              new Date(
                assignment.created_at
              )
            )
            === targetDate
          );
        }
      );
    },
    [
      historyAssignments,
      filterMode,
      selectedDate,
    ]
  );


  const showToday = () => {
    setSelectedDate(
      getLocalDateValue(new Date())
    );

    setFilterMode("today");
  };


  const showAll = () => {
    setFilterMode("all");
  };


  const handleDateChange = (event) => {
    setSelectedDate(
      event.target.value
    );

    setFilterMode("date");
  };


  return (
    <AppLayout>
      <section className="page-heading">
        <h2>
          {user.role === "DRIVER"
            ? "My Dispatch History"
            : "Dispatch History"}
        </h2>

        <p>
          Previous completed, rejected and
          cancelled dispatch assignments.
        </p>
      </section>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <section className="form-card">
        <div className="form-row">
          <label>
            History date

            <input
              type="date"
              value={selectedDate}
              onChange={handleDateChange}
            />
          </label>

          <div className="dispatch-actions">
            <button
              className={
                filterMode === "today"
                  ? "action-button"
                  : "secondary-button"
              }
              type="button"
              onClick={showToday}
            >
              Today
            </button>

            <button
              className={
                filterMode === "all"
                  ? "action-button"
                  : "secondary-button"
              }
              type="button"
              onClick={showAll}
            >
              All History
            </button>
          </div>
        </div>

        <p className="empty-note">
          {filterMode === "all"
            ? "Showing all dispatch history."
            : filterMode === "today"
              ? "Showing today's dispatch history."
              : (
                `Showing dispatch history for ${selectedDate}.`
              )}
        </p>
      </section>


      {loading ? (
        <div className="page-message">
          Loading dispatch history...
        </div>
      ) : filteredHistory.length === 0 ? (
        <div className="route-card">
          No dispatch history found for
          the selected period.
        </div>
      ) : (
        <section className="dispatch-list">
          {filteredHistory.map(
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

                  {user.role
                    === "DISPATCHER" && (
                    <p>
                      Driver:{" "}
                      <strong>
                        {
                          assignment
                            .driver_name
                        }
                      </strong>
                    </p>
                  )}

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
                    Created:{" "}
                    {new Date(
                      assignment.created_at
                    ).toLocaleString()}
                  </small>
                </div>
              </article>
            )
          )}
        </section>
      )}
    </AppLayout>
  );
}