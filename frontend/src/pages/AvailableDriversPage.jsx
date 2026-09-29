import {
  Navigate,
  useCallback,
  useEffect,
  useState,
} from "react";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";


export default function AvailableDriversPage() {
  const { user } = useAuth();

  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");


  const loadDrivers = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
      }

      setError("");

      try {
        const response = await api.get(
          "/transport/drivers/available/"
        );

        setDrivers(response.data);
      } catch {
        setError(
          "Available drivers could not be loaded."
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
    loadDrivers();

    const interval = window.setInterval(
      () => {
        loadDrivers(true);
      },
      10000
    );

    return () => {
      window.clearInterval(interval);
    };
  }, [loadDrivers]);


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
        <h2>Available Drivers</h2>

        <p>
          Drivers currently available for
          dispatch assignment.
        </p>
      </section>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {loading ? (
        <div className="page-message">
          Loading available drivers...
        </div>
      ) : drivers.length === 0 ? (
        <div className="route-card">
          No drivers are currently available.
        </div>
      ) : (
        <section className="dispatch-list">
          {drivers.map((driver, index) => (
            <article
                className="dispatch-card"
                key={driver.id}
            >
                <div>
                <h3>
                    #{index + 1}{" "}
                    {driver.full_name}
                </h3>

                <p>
                    Number plate:{" "}
                    <strong>
                    {driver.number_plate}
                    </strong>
                </p>

                <p>
                  <strong>Email:</strong>{" "}
                  {driver.email}
                </p>

                {driver.phone_number && (
                    <p>
                    Phone:{" "}
                    {driver.phone_number}
                    </p>
                )}
                </div>
            </article>
            ))}
        </section>
      )}
    </AppLayout>
  );
}