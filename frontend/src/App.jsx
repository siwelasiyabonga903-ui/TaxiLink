import {
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";

import ChangePasswordPage from "./pages/ChangePasswordPage";
import DashboardPage from "./pages/DashboardPage";
import DispatchPage from "./pages/DispatchPage";
import DriversPage from "./pages/DriversPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import RegisterPage from "./pages/RegisterPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import RoutesPage from "./pages/RoutesPage";
import DemandPage from "./pages/DemandPage";
import AvailableDriversPage from "./pages/AvailableDriversPage";
import ActiveDispatchesPage from "./pages/ActiveDispatchesPage";
import DispatchHistoryPage from "./pages/DispatchHistoryPage";

import { useAuth } from "./context/AuthContext";


function DriverPasswordGate({
  children,
}) {
  const { user, loading } = useAuth();

  const location = useLocation();

  if (loading) {
    return (
      <div className="page-message">
        Loading TaxiLink...
      </div>
    );
  }

  const passwordChangeRequired =
    user?.role === "DRIVER"
    && user.must_change_password;

  if (
    passwordChangeRequired
    && location.pathname
      !== "/change-password"
  ) {
    return (
      <Navigate
        to="/change-password"
        replace
      />
    );
  }

  return children;
}


export default function App() {
  return (
    <DriverPasswordGate>
      <Routes>
        <Route
          path="/"
          element={
            <Navigate
              to="/dashboard"
              replace
            />
          }
        />

        <Route
          path="/login"
          element={<LoginPage />}
        />

        <Route
          path="/register"
          element={<RegisterPage />}
        />

        <Route
          path="/forgot-password"
          element={<ForgotPasswordPage />}
        />

        <Route
          path="/reset-password"
          element={<ResetPasswordPage />}
        />

        <Route
          path="/dispatch/history"
          element={
            <ProtectedRoute>
              <DispatchHistoryPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/dispatch/active"
          element={
            <ProtectedRoute>
              <ActiveDispatchesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/dispatch"
          element={
            <ProtectedRoute>
              <DispatchPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/drivers"
          element={
            <ProtectedRoute>
              <DriversPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/routes"
          element={
            <ProtectedRoute>
              <RoutesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/demand"
          element={
            <ProtectedRoute>
              <DemandPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/available-drivers"
          element={
            <ProtectedRoute>
              <AvailableDriversPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="*"
          element={
            <Navigate
              to="/dashboard"
              replace
            />
          }
        />
      </Routes>
    </DriverPasswordGate>
  );
}