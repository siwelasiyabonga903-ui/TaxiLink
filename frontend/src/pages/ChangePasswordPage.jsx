import { useState } from "react";

import {
  Navigate,
  useNavigate,
} from "react-router-dom";

import { useAuth } from "../context/AuthContext";


const initialForm = {
  current_password: "",
  new_password: "",
  new_password_confirm: "",
};


function extractError(
  error,
  fallback
) {
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


export default function ChangePasswordPage() {
  const {
    user,
    changeDriverPassword,
    logout,
  } = useAuth();

  const navigate = useNavigate();

  const [form, setForm] = useState(
    initialForm
  );

  const [
    submitting,
    setSubmitting,
  ] = useState(false);

  const [error, setError] = useState("");


  if (
    user?.role !== "DRIVER"
    || !user.must_change_password
  ) {
    return (
      <Navigate
        to="/dashboard"
        replace
      />
    );
  }


  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]:
        event.target.value,
    });
  };


  const handleSubmit = async (
    event
  ) => {
    event.preventDefault();

    setError("");
    setSubmitting(true);

    try {
      await changeDriverPassword(
        form
      );

      navigate(
        "/dashboard",
        {
          replace: true,
        }
      );
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Password could not be changed."
        )
      );
    } finally {
      setSubmitting(false);
    }
  };


  const handleLogout = async () => {
    await logout();

    navigate(
      "/login",
      {
        replace: true,
      }
    );
  };


  return (
    <div className="auth-page">
      <form
        className="auth-card"
        onSubmit={handleSubmit}
      >
        <h1>Change your password</h1>

        <p>
          Your Dispatcher created your
          account with a temporary password.
          Choose your own password before
          continuing to TaxiLink.
        </p>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <input
          name="current_password"
          type="password"
          placeholder="Temporary password"
          value={
            form.current_password
          }
          onChange={handleChange}
          autoComplete="current-password"
          required
        />

        <input
          name="new_password"
          type="password"
          placeholder="New password"
          value={
            form.new_password
          }
          onChange={handleChange}
          autoComplete="new-password"
          minLength="8"
          required
        />

        <input
          name="new_password_confirm"
          type="password"
          placeholder="Confirm new password"
          value={
            form.new_password_confirm
          }
          onChange={handleChange}
          autoComplete="new-password"
          minLength="8"
          pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}"
          title="Use at least 8 characters with uppercase, lowercase, a number, and a special character."
          required
        />

        <small>
          At least 8 characters, including uppercase,
          lowercase, a number, and a special character.
        </small>

        <button
          type="submit"
          disabled={submitting}
        >
          {submitting
            ? "Changing password..."
            : "Change Password"}
        </button>

        <button
          className="secondary-button"
          type="button"
          disabled={submitting}
          onClick={handleLogout}
        >
          Log out
        </button>
      </form>
    </div>
  );
}