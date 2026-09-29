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

  const [username, setUsername] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [error, setError] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);

  const [showResend, setShowResend] =
    useState(false);

  const [
    verificationEmail,
    setVerificationEmail,
  ] = useState(
    location.state?.verificationEmail
    || ""
  );

  const [resending, setResending] =
    useState(false);

  const [
    resendMessage,
    setResendMessage,
  ] = useState("");


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
        + "has expired. Request a new link."
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


  const handleResendVerification =
    async () => {
      const email =
        verificationEmail
          .trim()
          .toLowerCase();

      setError("");
      setResendMessage("");

      if (!email) {
        setError(
          "Enter your email address."
        );

        return;
      }

      setResending(true);

      try {
        const response = await api.post(
          "/accounts/verify-email/resend/",
          { email }
        );

        setResendMessage(
          response.data?.detail
          || (
            "If an unverified account exists, "
            + "a confirmation link has been sent."
          )
        );
      } catch (requestError) {
        const data =
          requestError.response?.data;

        const firstError = data
          ? Object.values(data).flat()[0]
          : null;

        setError(
          typeof data?.detail === "string"
            ? data.detail
            : String(
                firstError
                || (
                  "The confirmation email could "
                  + "not be sent. Try again later."
                )
              )
        );
      } finally {
        setResending(false);
      }
    };


  const handleSubmit = async (event) => {
    event.preventDefault();

    setError("");
    setSubmitting(true);

    try {
      await login(
        username.trim(),
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
        setError(apiMessage);
        setShowResend(true);
      } else if (responseStatus === 401) {
        setError(
          "Username or password is incorrect."
        );

        setShowResend(false);
      } else {
        setError(
          typeof apiMessage === "string"
            ? apiMessage
            : (
              "Login could not be completed. "
              + "Please try again."
            )
        );

        setShowResend(false);
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
          value={username}
          onChange={(event) =>
            setUsername(
              event.target.value
            )
          }
          placeholder="Username"
          autoComplete="username"
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

        <button
          type="button"
          onClick={() => {
            setShowResend(
              (current) => !current
            );

            setError("");
            setResendMessage("");
          }}
        >
          Resend confirmation email
        </button>

        {showResend && (
          <div>
            <input
              type="email"
              value={verificationEmail}
              onChange={(event) =>
                setVerificationEmail(
                  event.target.value
                )
              }
              placeholder="Registration email"
              autoComplete="email"
              aria-label="Registration email"
            />

            <button
              type="button"
              disabled={resending}
              onClick={
                handleResendVerification
              }
            >
              {resending
                ? "Sending..."
                : "Send confirmation link"}
            </button>
          </div>
        )}

        {resendMessage && (
          <div className="success-message">
            {resendMessage}
          </div>
        )}

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