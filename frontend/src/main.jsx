import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import { WorkPeekProvider } from "./components/WorkPeekProvider.jsx";
import HallPage from "./pages/HallPage.jsx";
import JoinPage from "./pages/JoinPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import PeoplePage from "./pages/PeoplePage.jsx";
import QueuePage from "./pages/QueuePage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import SearchPage from "./pages/SearchPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import WorkPage from "./pages/WorkPage.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <WorkPeekProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/join" element={<JoinPage />} />
          <Route path="/" element={<App />}>
            <Route index element={<HallPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="works/:id" element={<WorkPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="queue" element={<QueuePage />} />
            <Route path="people" element={<PeoplePage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WorkPeekProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
