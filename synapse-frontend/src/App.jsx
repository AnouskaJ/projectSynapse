// src/App.jsx
import { Routes, Route } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Scenario from "./pages/Scenario.jsx";
import GrabCar from "./pages/GrabCar.jsx";          // ← add this
import Login from "./pages/Login.jsx";
import ProtectedRoute from "./components/auth/ProtectedRoute.jsx";
import Shell from "./components/layout/Shell.jsx";
import "./styles/grabcar.css";

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Protected */}
      <Route element={<ProtectedRoute />}>
        {/* (optional) wrap Home with Shell for consistent chrome */}
        <Route path="/" element={<Home />} />

        {/* Specific route goes before the param route */}
        <Route path="/service/grabcar" element={<GrabCar />} />

        {/* Fallback for other services still using the old Scenario page */}
        <Route path="/service/:service" element={<Shell><Scenario /></Shell>} />

        <Route path="/custom" element={<Shell><Scenario isCustom /></Shell>} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Login />} />
    </Routes>
  );
}
