import { useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";


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


export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] =
    useState("");
  const [error, setError] =
    useState("");
  const [submitting, setSubmitting] =
    useState(false);


  const handleSubmit = async (event) => {
    event.preventDefault();

    setError("");
    setMessage("");
    setSubmitting(true);

    try {
      const response = await api.post(
        "/accounts/password-reset/",
        {
          email: email
            .trim()
            .toLowerCase(),
        }
      );

      setMessage(response.data.detail);
      setEmail("");
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Password reset instructions could not be requested."
        )
      );
    } finally {
      setSubmitting(false);
    }
  };


  return (
    <div className="auth-page">
      <form
        className="auth-card"
        onSubmit={handleSubmit}
      >
        <h1>Forgot Password</h1>

        <p>
          Enter the email address registered
          with your TaxiLink account.
        </p>

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

        <input
          type="email"
          value={email}
          onChange={(event) =>
            setEmail(event.target.value)
          }
          placeholder="Email address"
          autoComplete="email"
          required
        />

        <button
          type="submit"
          disabled={submitting}
        >
          {submitting
            ? "Sending..."
            : "Send Reset Instructions"}
        </button>

        <p>
          Remember your password?{" "}
          <Link to="/login">
            Back to login
          </Link>
        </p>
      </form>
    </div>
  );
}