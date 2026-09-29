import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";


const initialForm = {
  first_name: "",
  last_name: "",
  email: "",
  phone_number: "",
  password: "",
  password_confirm: "",
};


export default function RegisterPage() {
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { registerPassenger } = useAuth();
  const navigate = useNavigate();


  const handleChange = (event) => {
  const { name, value } = event.target;

  const nextValue =
    name === "phone_number"
      ? value.replace(/\D/g, "").slice(0, 10)
      : value;

  setForm((current) => ({
    ...current,
    [name]: nextValue,
  }));
};


  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      const response = await registerPassenger(form);

      navigate("/login", {
        replace: true,
        state: {
          message:
            response.data?.detail
            || (
              "Registration successful. "
              + "Check your email to confirm your account."
            ),
        },
      });
    } catch (requestError) {
      const data = requestError.response?.data;

      if (data) {
        const firstError = Object.values(data).flat()[0];
        setError(String(firstError));
      } else {
        setError("Registration failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };


  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Create passenger account</h1>
        <p>Register to access TaxiLink waiting services.</p>

        {error && <div className="error-message">{error}</div>}


        <div className="form-row">
          <input
            name="first_name"
            placeholder="First name"
            value={form.first_name}
            onChange={handleChange}
            required
          />

          <input
            name="last_name"
            placeholder="Last name"
            value={form.last_name}
            onChange={handleChange}
            required
          />
        </div>

        <input
          name="email"
          type="email"
          placeholder="Email address"
          value={form.email}
          onChange={handleChange}
          required
          autoComplete="email"
        />

        <input
          name="phone_number"
          type="tel"
          inputMode="numeric"
          placeholder="Phone number"
          value={form.phone_number}
          onChange={handleChange}
          pattern="0[0-9]{9}"
          maxLength="10"
          title="Enter a 10-digit phone number starting with 0."
          autoComplete="tel"
          required
        />

        <input
          name="password"
          type="password"
          placeholder="Password"
          value={form.password}
          onChange={handleChange}
          required
          autoComplete="new-password"
          minLength="8"
          pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}"
          title="Use at least 8 characters with uppercase, lowercase, a number, and a special character."
        />

        <small>
          At least 8 characters, including uppercase,
          lowercase, a number, and a special character.
        </small>

        <input
          name="password_confirm"
          type="password"
          placeholder="Confirm password"
          value={form.password_confirm}
          onChange={handleChange}
          required
          autoComplete="new-password"
          minLength="8"
        />

        <button disabled={submitting} type="submit">
          {submitting ? "Creating account..." : "Register"}
        </button>

        <p>
          Already registered? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  );
}