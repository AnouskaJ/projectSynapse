// src/App.jsx
import { Routes, Route } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Scenario from "./pages/Scenario.jsx";
import GrabCar from "./pages/GrabCar.jsx";          // ← add this
import Login from "./pages/Login.jsx";
import ProtectedRoute from "./components/auth/ProtectedRoute.jsx";
import Shell from "./components/layout/Shell.jsx";
import "./styles/grabCar.css";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Home />} />

        {/* ✅ Changed path */}
        <Route path="/service/agent" element={<GrabCar />} />

        <Route path="/service/:service" element={<Shell><Scenario /></Shell>} />
        <Route path="/custom" element={<Shell><Scenario isCustom /></Shell>} />
      </Route>

      <Route path="*" element={<Login />} />
    </Routes>
  );
}