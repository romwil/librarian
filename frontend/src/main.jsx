import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import App from "./App.jsx";
import { WorkPeekProvider } from "./components/WorkPeekProvider.jsx";
import BrowsePage from "./pages/BrowsePage.jsx";
import HallPage from "./pages/HallPage.jsx";
import WantedPage from "./pages/WantedPage.jsx";
import JoinPage from "./pages/JoinPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import PeoplePage from "./pages/PeoplePage.jsx";
import QueuePage from "./pages/QueuePage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import SearchPage from "./pages/SearchPage.jsx";
import MaintainPage from "./pages/MaintainPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import InboxPage from "./pages/InboxPage.jsx";
import NotificationsPage from "./pages/NotificationsPage.jsx";
import NotedPage from "./pages/NotedPage.jsx";
import WorkPage from "./pages/WorkPage.jsx";
import CardPage from "./pages/CardPage.jsx";
import "./styles.css";

function FindToSearch() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: "/search", search }} replace />;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <WorkPeekProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/join" element={<JoinPage />} />
          <Route path="/" element={<App />}>
            <Route index element={<HallPage />} />
            <Route path="browse" element={<BrowsePage />} />
            <Route path="wanted" element={<WantedPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="noted" element={<NotedPage />} />
            <Route path="find" element={<FindToSearch />} />
            <Route path="card" element={<CardPage />} />
            <Route path="works/:id" element={<WorkPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="queue" element={<QueuePage />} />
            <Route path="people" element={<PeoplePage />} />
            <Route path="maintain" element={<MaintainPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="inbox" element={<InboxPage />} />
            <Route path="notifications" element={<NotificationsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WorkPeekProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
