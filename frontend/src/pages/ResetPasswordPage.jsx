import { useState } from "react";

import {
  Link,
  useNavigate,
  useSearchParams,
} from "react-router-dom";

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


export default function ResetPasswordPage() {
  const navigate = useNavigate();

  const [searchParams] =
    useSearchParams();

  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] =
    useState("");

  const [
    newPasswordConfirm,
    setNewPasswordConfirm,
  ] = useState("");

  const [error, setError] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);


  const invalidLink = !uid || !token;


  const handleSubmit = async (event) => {
    event.preventDefault();

    if (invalidLink) {
      setError(
        "This password reset link is invalid."
      );

      return;
    }

    setError("");
    setSubmitting(true);

    try {
      const response = await api.post(
        "/accounts/password-reset/confirm/",
        {
          uid,
          token,
          new_password: newPassword,
          new_password_confirm:
            newPasswordConfirm,
        }
      );

      navigate(
        "/login",
        {
          replace: true,
          state: {
            message: response.data.detail,
          },
        }
      );
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Your password could not be reset."
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
        <h1>Reset Password</h1>

        {invalidLink ? (
          <>
            <div className="error-message">
              This password reset link is
              invalid or incomplete.
            </div>

            <p>
              <Link to="/forgot-password">
                Request a new reset link
              </Link>
            </p>
          </>
        ) : (
          <>
            <p>
              Choose a new password for your
              TaxiLink account.
            </p>

            {error && (
              <div className="error-message">
                {error}
              </div>
            )}

            <input
              type="password"
              value={newPassword}
              onChange={(event) =>
                setNewPassword(
                  event.target.value
                )
              }
              placeholder="New password"
              autoComplete="new-password"
              minLength="8"
              required
            />

            <input
              type="password"
              value={newPasswordConfirm}
              onChange={(event) =>
                setNewPasswordConfirm(
                  event.target.value
                )
              }
              placeholder="Confirm new password"
              autoComplete="new-password"
              minLength="8"
              required
              pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}"
              title="Use at least 8 characters with uppercase, lowercase, a number, and a special character."
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
                ? "Resetting..."
                : "Reset Password"}
            </button>
          </>
        )}

        <p>
          <Link to="/login">
            Back to login
          </Link>
        </p>
      </form>
    </div>
  );
}