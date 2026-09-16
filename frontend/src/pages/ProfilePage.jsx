import { useState } from "react";

import { useNavigate } from "react-router-dom";

import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";


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


const initialPasswordForm = {
  current_password: "",
  new_password: "",
  new_password_confirm: "",
};


export default function ProfilePage() {
  const {
    user,
    updateProfile,
    changeAccountPassword,
    logout,
  } = useAuth();

  const navigate = useNavigate();

  const [form, setForm] = useState({
    first_name: user.first_name ?? "",
    last_name: user.last_name ?? "",
    phone_number: user.phone_number ?? "",
  });

  const [
    passwordForm,
    setPasswordForm,
  ] = useState(initialPasswordForm);

  const [
    changingPassword,
    setChangingPassword,
  ] = useState(false);

  const [message, setMessage] =
    useState("");

  const [error, setError] =
    useState("");

  const [
    passwordError,
    setPasswordError,
  ] = useState("");


  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]:
        event.target.value,
    });
  };


  const handlePasswordChange = (
    event
  ) => {
    setPasswordForm({
      ...passwordForm,
      [event.target.name]:
        event.target.value,
    });
  };


  const handleSubmit = async (
    event
  ) => {
    event.preventDefault();

    setMessage("");
    setError("");

    try {
      await updateProfile(form);

      setMessage(
        "Profile updated successfully."
      );
    } catch {
      setError(
        "The profile could not be updated."
      );
    }
  };


  const handlePasswordSubmit = async (
    event
  ) => {
    event.preventDefault();

    setPasswordError("");
    setMessage("");
    setChangingPassword(true);

    try {
      await changeAccountPassword(
        passwordForm
      );

      await logout();

      navigate(
        "/login",
        {
          replace: true,
          state: {
            message:
              "Password changed successfully. "
              + "Please log in with your new password.",
          },
        }
      );
    } catch (requestError) {
      setPasswordError(
        extractError(
          requestError,
          "Password could not be changed."
        )
      );
    } finally {
      setChangingPassword(false);
    }
  };


  return (
    <AppLayout>
      <section className="profile-card">
        <h2>My Profile</h2>

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

        <form onSubmit={handleSubmit}>
          <label>
            Username

            <input
              value={user.username}
              disabled
            />
          </label>

          <label>
            Email

            <input
              value={user.email}
              disabled
            />
          </label>

          <label>
            Role

            <input
              value={user.role_display}
              disabled
            />
          </label>

          <label>
            First name

            <input
              name="first_name"
              value={form.first_name}
              onChange={handleChange}
              required
            />
          </label>

          <label>
            Last name

            <input
              name="last_name"
              value={form.last_name}
              onChange={handleChange}
              required
            />
          </label>

          <label>
            Phone number

            <input
              name="phone_number"
              value={form.phone_number}
              onChange={handleChange}
              required
            />
          </label>

          <button type="submit">
            Save changes
          </button>
        </form>
      </section>

      <section className="profile-card">
        <h2>Change Password</h2>

        <p>
          Enter your current password and
          choose a new password.
        </p>

        {passwordError && (
          <div className="error-message">
            {passwordError}
          </div>
        )}

        <form
          onSubmit={handlePasswordSubmit}
        >
          <label>
            Current password

            <input
              name="current_password"
              type="password"
              value={
                passwordForm
                  .current_password
              }
              onChange={
                handlePasswordChange
              }
              autoComplete="current-password"
              required
            />
          </label>

          <label>
            New password

            <input
              name="new_password"
              type="password"
              value={
                passwordForm
                  .new_password
              }
              onChange={
                handlePasswordChange
              }
              autoComplete="new-password"
              minLength="8"
              required
            />
          </label>

          <label>
            Confirm new password

            <input
              name="new_password_confirm"
              type="password"
              value={
                passwordForm
                  .new_password_confirm
              }
              onChange={
                handlePasswordChange
              }
              autoComplete="new-password"
              minLength="8"
              required
            />
          </label>

          <button
            type="submit"
            disabled={changingPassword}
          >
            {changingPassword
              ? "Changing password..."
              : "Change Password"}
          </button>
        </form>
      </section>
    </AppLayout>
  );
}