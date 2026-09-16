import { useState } from "react";

import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { useAuth } from "../context/AuthContext";


export default function LoginPage() {
  const [username, setUsername] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [error, setError] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);

  const { user, login } = useAuth();

  const navigate = useNavigate();
  const location = useLocation();


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

    setError("");
    setSubmitting(true);

    try {
      await login(
        username,
        password
      );

      navigate("/dashboard");
    } catch {
      setError(
        "Invalid username or password."
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
        <h1>TaxiLink</h1>

        <p>
          Sign in to continue.
        </p>

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