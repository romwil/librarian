import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function AppChrome({ user, features, children }) {
  const navigate = useNavigate();
  const op = user.role === "owner" || user.role === "op";
  const owner = user.role === "owner";

  async function logout() {
    await api.logout();
    navigate("/login");
  }

  return (
    <div className="room">
      <header className="topbar">
        <NavLink to="/" className="mark">
          <span className="mark-lamp" aria-hidden="true" />
          Librarian
        </NavLink>
        <nav className="topnav">
          <NavLink to="/" end>
            Hall
          </NavLink>
          <NavLink to="/search">Search</NavLink>
          {op ? <NavLink to="/review">Review</NavLink> : null}
          {op ? <NavLink to="/queue">Queue</NavLink> : null}
          {owner ? <NavLink to="/people">People</NavLink> : null}
          {owner ? <NavLink to="/settings">Settings</NavLink> : null}
        </nav>
        <button type="button" className="ghost" onClick={logout}>
          {user.display_name}
        </button>
      </header>
      <main className="page">{children}</main>
      <nav className="bottombar" aria-label="Mobile">
        <NavLink to="/" end>
          Hall
        </NavLink>
        <NavLink to="/search">Search</NavLink>
        <NavLink to="/search?shelf=favorites">Favorites</NavLink>
        <span>{user.display_name}</span>
      </nav>
      {features?.household_name ? <span className="sr-only">{features.household_name}</span> : null}
    </div>
  );
}
