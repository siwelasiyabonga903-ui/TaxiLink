import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";


const initialForm = {
  username: "",
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
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  };


  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await registerPassenger(form);
      navigate("/login", {
        state: {
          message: "Registration successful. Please log in.",
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

        <input
          name="username"
          placeholder="Username"
          value={form.username}
          onChange={handleChange}
          required
        />

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
        />

        <input
          name="phone_number"
          placeholder="Phone number"
          value={form.phone_number}
          onChange={handleChange}
          required
        />

        <input
          name="password"
          type="password"
          placeholder="Password"
          value={form.password}
          onChange={handleChange}
          required
        />

        <input
          name="password_confirm"
          type="password"
          placeholder="Confirm password"
          value={form.password_confirm}
          onChange={handleChange}
          required
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