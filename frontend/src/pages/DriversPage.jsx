import {
  Navigate,
  useCallback,
  useEffect,
  useState,
} from "react";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";


const initialDriverForm = {
  first_name: "",
  last_name: "",
  email: "",
  phone_number: "",
  number_plate: "",
};


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


export default function DriversPage() {
  const { user } = useAuth();

  const [drivers, setDrivers] =
    useState([]);

  const [driverForm, setDriverForm] =
    useState(initialDriverForm);

  const [
    addDriverOpen,
    setAddDriverOpen,
  ] = useState(false);

  const [
    generatedDriverCredentials,
    setGeneratedDriverCredentials,
  ] = useState(null);

  const [
    resetDriverCredentials,
    setResetDriverCredentials,
  ] = useState(null);

  const [
    resettingDriverId,
    setResettingDriverId,
  ] = useState(null);

  const [
    creatingDriver,
    setCreatingDriver,
  ] = useState(false);

  const [loading, setLoading] =
    useState(true);

  const [message, setMessage] =
    useState("");

  const [error, setError] =
    useState("");


  const loadDrivers = useCallback(
    async () => {
      try {
        const response = await api.get(
          "/accounts/drivers/"
        );

        setDrivers(response.data);
      } catch (requestError) {
        setError(
          extractError(
            requestError,
            "Driver accounts could not be loaded."
          )
        );
      } finally {
        setLoading(false);
      }
    },
    []
  );


  useEffect(() => {
    if (user.role === "DISPATCHER") {
      loadDrivers();
    }
  }, [
    user.role,
    loadDrivers,
  ]);


  useEffect(() => {
    const modalOpen =
      addDriverOpen
      || Boolean(
        generatedDriverCredentials
      )
      || Boolean(
        resetDriverCredentials
      );

    if (modalOpen) {
      document.body.style.overflow =
        "hidden";
    } else {
      document.body.style.overflow =
        "";
    }

    return () => {
      document.body.style.overflow =
        "";
    };
  }, [
    addDriverOpen,
    generatedDriverCredentials,
    resetDriverCredentials,
  ]);


  if (user.role !== "DISPATCHER") {
    return (
      <Navigate
        to="/dashboard"
        replace
      />
    );
  }


  const openAddDriver = () => {
    setError("");
    setMessage("");

    setDriverForm(
      initialDriverForm
    );

    setAddDriverOpen(true);
  };


  const closeAddDriver = () => {
    if (creatingDriver) {
      return;
    }

    setAddDriverOpen(false);

    setDriverForm(
      initialDriverForm
    );
  };


  const handleDriverChange = (
  event
) => {
  const {
    name,
    value,
  } = event.target;

  let nextValue = value;

  if (name === "number_plate") {
    nextValue = value.toUpperCase();
  }

  if (name === "phone_number") {
    nextValue = value
      .replace(/\D/g, "")
      .slice(0, 10);
  }

  setDriverForm(
    (current) => ({
      ...current,
      [name]: nextValue,
    })
  );
};


  const copyPassword = async (
    password
  ) => {
    if (!password) {
      return;
    }

    try {
      await navigator.clipboard.writeText(
        password
      );

      setError("");

      setMessage(
        "Temporary password copied."
      );
    } catch {
      setError(
        "Temporary password could not be copied automatically."
      );
    }
  };


  const addDriver = async (
    event
  ) => {
    event.preventDefault();

    setError("");
    setMessage("");
    setGeneratedDriverCredentials(
      null
    );

    setCreatingDriver(true);

    try {
      const response = await api.post(
        "/accounts/drivers/register/",
        {
          ...driverForm,

          first_name:
            driverForm.first_name.trim(),

          last_name:
            driverForm.last_name.trim(),

          email:
            driverForm.email
              .trim()
              .toLowerCase(),

          phone_number:
            driverForm.phone_number.trim(),

          number_plate:
            driverForm.number_plate.trim(),
        }
      );

      setGeneratedDriverCredentials({
        email:
          response.data.email,

        temporaryPassword:
          response.data.temporary_password,
      });

      setDriverForm(
        initialDriverForm
      );

      setAddDriverOpen(false);

      setMessage(
        "Driver added successfully."
      );

      await loadDrivers();
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "The Driver could not be added."
        )
      );
    } finally {
      setCreatingDriver(false);
    }
  };


  const resetTemporaryPassword =
    async (driver) => {
      setError("");
      setMessage("");

      setResetDriverCredentials(
        null
      );

      setResettingDriverId(
        driver.id
      );

      try {
        const response =
          await api.post(
            `/accounts/drivers/${driver.id}/reset-temporary-password/`,
            {}
          );

        setResetDriverCredentials({
          driverId:
            driver.id,

          email:
            response.data.email,

          temporaryPassword:
            response.data
              .temporary_password,
        });

        setMessage(
          "Temporary password regenerated successfully."
        );

        await loadDrivers();
      } catch (requestError) {
        setError(
          extractError(
            requestError,
            "Temporary password could not be regenerated."
          )
        );
      } finally {
        setResettingDriverId(
          null
        );
      }
    };


  return (
    <AppLayout>
      <section className="page-heading">
        <h2>
          Driver Management
        </h2>

        <p>
          Add TaxiLink Drivers and manage
          temporary passwords when needed.
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


      <div className="route-page-actions">
        <button
          className="action-button"
          type="button"
          onClick={
            openAddDriver
          }
        >
          + Add Driver
        </button>
      </div>


      <section className="dispatch-list">
        <h3>
          Registered Drivers
        </h3>


        {loading && (
          <div className="page-message">
            Loading Drivers...
          </div>
        )}


        {!loading
          && drivers.length === 0 && (
          <div className="route-card">
            No Driver accounts have been
            registered yet.
          </div>
        )}


        {!loading
          && drivers.map(
            (driver) => (
              <article
                className="dispatch-card"
                key={driver.id}
              >
                <div>
                  <h4>
                    {driver.full_name}
                  </h4>

                  <p>
                    Number plate:{" "}

                    <strong>
                      {driver.number_plate}
                    </strong>
                  </p>

                  <p>
                    Email:{" "}

                    {driver.email}
                  </p>

                  <p>
                    Phone:{" "}

                    {driver.phone_number}
                  </p>
                </div>


                {driver
                  .must_change_password && (
                  <div className="dispatch-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={
                        resettingDriverId
                        === driver.id
                      }
                      onClick={() =>
                        resetTemporaryPassword(
                          driver
                        )
                      }
                    >
                      {resettingDriverId
                        === driver.id
                        ? "Regenerating..."
                        : (
                          "Regenerate "
                          + "Temporary Password"
                        )}
                    </button>
                  </div>
                )}
              </article>
            )
          )}
      </section>


      {addDriverOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={
            closeAddDriver
          }
        >
          <section
            className="dispatch-modal driver-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Add Driver
            </h3>

            <p className="empty-note">
              TaxiLink will generate a
              temporary password for the
              Driver.
            </p>


            <form
              onSubmit={
                addDriver
              }
            >

              <div className="form-row">
                <label>
                  First name

                  <input
                    name="first_name"
                    value={
                      driverForm
                        .first_name
                    }
                    onChange={
                      handleDriverChange
                    }
                    required
                  />
                </label>

                <label>
                  Last name

                  <input
                    name="last_name"
                    value={
                      driverForm
                        .last_name
                    }
                    onChange={
                      handleDriverChange
                    }
                    required
                  />
                </label>
              </div>


              <label>
                Email

                <input
                  name="email"
                  type="email"
                  value={
                    driverForm.email
                  }
                  onChange={
                    handleDriverChange
                  }
                  autoComplete="email"
                  required
                />
              </label>


              <label>
                Phone number

                <input
                  name="phone_number"
                  type="tel"
                  inputMode="numeric"
                  value={
                    driverForm.phone_number
                  }
                  onChange={
                    handleDriverChange
                  }
                  pattern="0[0-9]{9}"
                  maxLength="10"
                  title="Enter a 10-digit phone number starting with 0."
                  autoComplete="tel"
                  required
                />
              </label>


              <label>
                Number plate

                <input
                  name="number_plate"
                  value={
                    driverForm
                      .number_plate
                  }
                  onChange={
                    handleDriverChange
                  }
                  placeholder="ABC 123 L"
                  maxLength="20"
                  required
                />
              </label>


              <div className="dispatch-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={
                    creatingDriver
                  }
                  onClick={
                    closeAddDriver
                  }
                >
                  Cancel
                </button>

                <button
                  className="action-button"
                  type="submit"
                  disabled={
                    creatingDriver
                  }
                >
                  {creatingDriver
                    ? "Adding Driver..."
                    : "Add Driver"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}


      {generatedDriverCredentials && (
        <div
          className="modal-backdrop"
          onMouseDown={() =>
            setGeneratedDriverCredentials(
              null
            )
          }
        >
          <section
            className="dispatch-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Temporary Driver Password
            </h3>

            <p>
              Email:{" "}

              <strong>
                {
                  generatedDriverCredentials.email
                }
              </strong>
            </p>

            <p>
              Temporary password:{" "}

              <strong>
                {
                  generatedDriverCredentials
                    .temporaryPassword
                }
              </strong>
            </p>

            <p className="empty-note">
              Give this password to the
              Driver now. TaxiLink will not
              show it again after this popup
              is closed.
            </p>


            <div className="dispatch-actions">
              <button
                className="action-button"
                type="button"
                onClick={() =>
                  copyPassword(
                    generatedDriverCredentials
                      .temporaryPassword
                  )
                }
              >
                Copy Password
              </button>

              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setGeneratedDriverCredentials(
                    null
                  )
                }
              >
                Close
              </button>
            </div>
          </section>
        </div>
      )}


      {resetDriverCredentials && (
        <div
          className="modal-backdrop"
          onMouseDown={() =>
            setResetDriverCredentials(
              null
            )
          }
        >
          <section
            className="dispatch-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              New Temporary Password
            </h3>

            <p>
              Email:{" "}

              <strong>
                {
                  resetDriverCredentials.email
                }
              </strong>
            </p>

            <p>
              Temporary password:{" "}

              <strong>
                {
                  resetDriverCredentials
                    .temporaryPassword
                }
              </strong>
            </p>

            <p className="empty-note">
              Give this password to the
              Driver now. The previous
              temporary password no longer
              works.
            </p>


            <div className="dispatch-actions">
              <button
                className="action-button"
                type="button"
                onClick={() =>
                  copyPassword(
                    resetDriverCredentials
                      .temporaryPassword
                  )
                }
              >
                Copy Password
              </button>

              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setResetDriverCredentials(
                    null
                  )
                }
              >
                Close
              </button>
            </div>
          </section>
        </div>
      )}
    </AppLayout>
  );
}