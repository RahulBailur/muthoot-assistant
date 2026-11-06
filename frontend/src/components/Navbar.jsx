import { Link, NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

const LINKS = {
  customer: [
    { to: "/", label: "My loans" },
    { to: "/estimate", label: "Loan estimate" },
    { to: "/book", label: "Book a visit" },
    { to: "/help", label: "Help" },
  ],
  staff: [{ to: "/", label: "Branch queue" }],
  admin: [{ to: "/", label: "Analytics" }],
};

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header className="navbar">
      <Link to="/" className="brand">
        Gold Loan Assistant
      </Link>
      {user ? (
        <>
          <nav aria-label="Main">
            {LINKS[user.role].map((link) => (
              <NavLink key={link.to} to={link.to} end>
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="navbar-user">
            <span>
              {user.name} <span className="role-tag">{user.role}</span>
            </span>
            <button type="button" className="button quiet" onClick={logout}>
              Log out
            </button>
          </div>
        </>
      ) : (
        <nav aria-label="Main">
          <NavLink to="/login">Log in</NavLink>
        </nav>
      )}
    </header>
  );
}
