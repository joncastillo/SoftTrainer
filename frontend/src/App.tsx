import { Link, Route, Routes } from "react-router-dom";
import { HistoryPage } from "./pages/HistoryPage";
import { ProgressPage } from "./pages/ProgressPage";
import { SessionPage } from "./pages/SessionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SetupPage } from "./pages/SetupPage";

export default function App() {
  return (
    <div className="app">
      <nav className="topnav">
        <Link to="/" className="brand">SoftTrainer</Link>
        <div className="nav-links">
          <Link to="/">New session</Link>
          <Link to="/history">History</Link>
          <Link to="/progress">Progress</Link>
          <Link to="/settings">Settings</Link>
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<SetupPage />} />
        <Route path="/session/:id" element={<SessionPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </div>
  );
}
