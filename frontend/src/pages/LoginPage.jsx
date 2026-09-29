import { useState } from "react";

import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";

import api from "../api/client";
import { useAuth } from "../context/AuthContext";


export default function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const { user, login } = useAuth();

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [error, setError] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);

  const verificationStatus =
    new URLSearchParams(
      location.search
    ).get("verification");


  const verificationNotice = {
    success: {
      className: "success-message",

      message: (
        "Email confirmed successfully. "
        + "You can now sign in."
      ),
    },

    already: {
      className: "success-message",

      message: (
        "This email has already been confirmed. "
        + "You can sign in."
      ),
    },

    invalid: {
  className: "error-message",

  message: (
    "This confirmation link is invalid or "
    + "has expired. Sign in below to receive "
    + "a fresh confirmation link."
  ),
},
  }[verificationStatus];


  if (user) {
    return (
      <Navigate
        to="/dashboard"
        replace
      />
    );
  }

  const handleSubmit = async (event) => {
  event.preventDefault();

  const normalizedEmail =
    email.trim().toLowerCase();

  setError("");
  setSubmitting(true);

  try {
    await login(
      normalizedEmail,
      password
    );

    navigate("/dashboard");
  } catch (requestError) {
    const responseStatus =
      requestError.response?.status;

    const apiMessage =
      requestError.response?.data?.detail;

    const requiresConfirmation =
      typeof apiMessage === "string"
      && apiMessage
        .toLowerCase()
        .includes("confirm");

    if (requiresConfirmation) {
      try {
        await api.post(
          "/accounts/verify-email/resend/",
          {
            email: normalizedEmail,
          }
        );

        setError(
          "Confirm your email address before "
          + "logging in. A fresh confirmation "
          + "link has been sent to your email."
        );
      } catch {
        setError(apiMessage);
      }
    } else if (responseStatus === 401) {
      setError(
        "Email or password is incorrect."
      );
    } else {
      setError(
        typeof apiMessage === "string"
          ? apiMessage
          : (
            "Login could not be completed. "
            + "Please try again."
          )
      );
    }
  } finally {
    setSubmitting(false);
  }
};


  return (
    <div className="auth-page login-page">
      <aside
        className="login-intro"
        aria-label="About TaxiLink"
      >
        <span className="login-intro-tag">
          SMART TAXI DISPATCH
        </span>

        <h2>
          Every ride starts with a connection.
        </h2>

        <p>
          Passengers, drivers, and dispatchers
          in sync, from check-in to pickup.
        </p>
      </aside>

      <form
        className="auth-card"
        onSubmit={handleSubmit}
      >
        <h1>
          TaxiLink
        </h1>

        <p>
          Sign in to continue.
        </p>

        {verificationNotice && (
          <div
            className={
              verificationNotice.className
            }
          >
            {verificationNotice.message}
          </div>
        )}

        {location.state?.message && (
          <div className="success-message">
            {location.state.message}
          </div>
        )}

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <input
          value={email}
          onChange={(event) =>
            setEmail(
              event.target.value
            )
          }
          placeholder="Email address"
          type="email"
          autoComplete="email"
          required
        />

        <input
          value={password}
          onChange={(event) =>
            setPassword(
              event.target.value
            )
          }
          placeholder="Password"
          type="password"
          autoComplete="current-password"
          required
        />

        <button
          disabled={submitting}
          type="submit"
        >
          {submitting
            ? "Signing in..."
            : "Login"}
        </button>

        <p>
          <Link to="/forgot-password">
            Forgot password?
          </Link>
        </p>

        <p>
          New passenger?{" "}

          <Link to="/register">
            Register
          </Link>
        </p>
      </form>
    </div>
  );
}