import {
  NavLink,
  useNavigate,
} from "react-router-dom";

import PassengerLocationMonitor
  from "./PassengerLocationMonitor";

import { useAuth } from "../context/AuthContext";


export default function AppLayout({
  children,
}) {
  const { user, logout } = useAuth();

  const navigate = useNavigate();


  const handleLogout = async () => {
    await logout();

    navigate("/login");
  };


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>TaxiLink</h1>

          <small>
            Smart Taxi Demand Monitoring and Dispatch
          </small>
        </div>

        <nav>
          <NavLink to="/dashboard">
            Dashboard
          </NavLink>

          <NavLink to="/routes">
            Routes
          </NavLink>

          {user.role === "DISPATCHER" && (
            <NavLink to="/drivers">
              Drivers
            </NavLink>
          )}

          {user.role === "DRIVER" && (
            <NavLink to="/dispatch">
              Dispatch
            </NavLink>
          )}

          <NavLink to="/profile">
            Profile
          </NavLink>

          <button
            className="link-button"
            onClick={handleLogout}
            type="button"
          >
            Logout
          </button>
        </nav>
      </header>


      <main className="page-container">
        <div className="user-summary">
          Signed in as{" "}
          <strong>
            {user.username}
          </strong>
          {" · "}
          {user.role_display}
        </div>


        {user.role === "PASSENGER" && (
          <PassengerLocationMonitor />
        )}


        {children}
      </main>
    </div>
  );
}