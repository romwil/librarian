import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { api } from "./api.js";
import AppChrome from "./components/AppChrome.jsx";
import WhatsNewGate from "./components/WhatsNewGate.jsx";

export default function App() {
  const location = useLocation();
  const [user, setUser] = useState(undefined);
  const [features, setFeatures] = useState(null);
  const [reviewCount, setReviewCount] = useState(0);

  useEffect(() => {
    let alive = true;
    api
      .features()
      .then((data) => {
        if (alive) setFeatures(data);
      })
      .catch(() => {
        if (alive) setFeatures({ household_name: "The Hall" });
      });
    api
      .me()
      .then((data) => {
        if (alive) {
          setUser(data.user);
          setReviewCount(data.review_count || 0);
        }
      })
      .catch((error) => {
        if (alive) setUser(error.status === 401 ? null : null);
      });
    return () => {
      alive = false;
    };
  }, [location.pathname]);

  if (user === undefined) {
    return <div className="boot-lamp" aria-hidden="true" />;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppChrome user={user} features={features} reviewCount={reviewCount}>
      <WhatsNewGate />
      <Outlet context={{ user, features, setUser, reviewCount }} />
    </AppChrome>
  );
}
