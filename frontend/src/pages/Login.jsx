import { useState } from "react";
import { Navigate } from "react-router-dom";

import { errorMessage } from "../api";
import { useAuth } from "../context/AuthContext";

const PHONE = /^[6-9]\d{9}$/;
const PHONE_HINT = "Enter a 10-digit Indian mobile number.";

/** Customers sign in with a one-time code; branch staff and admins with a password. */
export default function Login() {
  const { user } = useAuth();
  const [mode, setMode] = useState("customer");

  if (user) return <Navigate to="/" replace />;

  return (
    <div className="auth-page">
      <div className="card form">
        <h1>Log in</h1>
        <div className="tabs" role="tablist" aria-label="Who is logging in">
          {[
            ["customer", "Customer"],
            ["staff", "Branch staff or admin"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              className={`button ${mode === value ? "primary" : "quiet"}`}
              onClick={() => setMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === "customer" ? <CustomerLogin /> : <StaffLogin />}
      </div>
    </div>
  );
}

function CustomerLogin() {
  const { requestOtp, verifyOtp } = useAuth();
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState(null);
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendCode(event) {
    event.preventDefault();
    setError("");
    if (!PHONE.test(phone)) return setError(PHONE_HINT);
    setBusy(true);
    try {
      setSent(await requestOtp(phone));
    } catch (err) {
      setError(errorMessage(err, "Could not send the code."));
    } finally {
      setBusy(false);
    }
  }

  async function checkCode(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await verifyOtp(phone, otp.trim(), name.trim());
    } catch (err) {
      setError(errorMessage(err, "Could not log in."));
      setBusy(false);
    }
  }

  if (!sent) {
    return (
      <form onSubmit={sendCode} noValidate>
        <label htmlFor="phone">Mobile number</label>
        <input
          id="phone"
          inputMode="numeric"
          autoComplete="tel-national"
          maxLength={10}
          value={phone}
          onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
        />
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? "Sending…" : "Send code"}
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={checkCode} noValidate>
      <p className="muted">
        We sent a 6-digit code to {sent.sent_to}. Type it in here only: the assistant will never ask
        for it.
      </p>
      {sent.demo_otp && (
        <p className="notice" role="status">
          Demo: there is no SMS, so your code is <strong>{sent.demo_otp}</strong>.
        </p>
      )}
      <label htmlFor="otp">Code</label>
      <input
        id="otp"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={otp}
        onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))}
      />
      <label htmlFor="name">Your name (first time only)</label>
      <input
        id="name"
        autoComplete="name"
        maxLength={80}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="button primary" disabled={busy || otp.length !== 6}>
        {busy ? "Checking…" : "Log in"}
      </button>
      <button
        type="button"
        className="button quiet"
        onClick={() => {
          setSent(null);
          setOtp("");
        }}
      >
        Use a different number
      </button>
    </form>
  );
}

function StaffLogin() {
  const { login } = useAuth();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    if (!PHONE.test(phone)) return setError(PHONE_HINT);
    setBusy(true);
    try {
      await login(phone, password);
    } catch (err) {
      setError(errorMessage(err, "Could not log in."));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <label htmlFor="staff-phone">Mobile number</label>
      <input
        id="staff-phone"
        inputMode="numeric"
        autoComplete="username"
        maxLength={10}
        value={phone}
        onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
      />
      <label htmlFor="password">Password</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="button primary" disabled={busy || !password}>
        {busy ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
