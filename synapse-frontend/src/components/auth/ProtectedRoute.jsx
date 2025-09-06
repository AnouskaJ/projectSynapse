import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider.jsx";

export default function ProtectedRoute() {
  const { user, ready } = useAuth();
  const loc = useLocation();

  if (!ready) return null; // or a loader/spinner

  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc }} />;
  }

  return <Outlet />;
}
