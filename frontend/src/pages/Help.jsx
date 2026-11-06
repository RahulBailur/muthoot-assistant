import { useCallback, useEffect, useState } from "react";

import api, { errorMessage } from "../api";
import { formatDate } from "../time";

const KINDS = { callback: "Call me back", complaint: "Complaint" };
const TICKET_STATUS = { open: "Open", in_progress: "Being handled", resolved: "Resolved" };

/** Find a branch, and raise a complaint or ask for a callback. */
export default function Help() {
  const [branches, setBranches] = useState([]);
  const [city, setCity] = useState("");
  const [tickets, setTickets] = useState([]);
  const [kind, setKind] = useState("callback");
  const [message, setMessage] = useState("");
  const [preferredTime, setPreferredTime] = useState("");
  const [branchId, setBranchId] = useState("");
  const [raised, setRaised] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadTickets = useCallback(async () => {
    try {
      setTickets((await api.get("/api/tickets/me")).data);
    } catch (err) {
      setError(errorMessage(err, "Could not load your requests."));
    }
  }, []);

  useEffect(() => {
    api
      .get("/api/branches")
      .then((response) => setBranches(response.data))
      .catch((err) => setError(errorMessage(err, "Could not load the branches.")));
    loadTickets();
  }, [loadTickets]);

  async function raise(event) {
    event.preventDefault();
    setError("");
    setRaised(null);
    if (message.trim().length < 3) {
      setError("Tell us briefly what it is about.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/api/tickets", {
        kind,
        message: message.trim(),
        ...(preferredTime.trim() && { preferred_time: preferredTime.trim() }),
        ...(branchId && { branch_id: branchId }),
      });
      setRaised(data);
      setMessage("");
      setPreferredTime("");
      await loadTickets();
    } catch (err) {
      setError(errorMessage(err, "Could not send your request."));
    } finally {
      setBusy(false);
    }
  }

  const shown = city ? branches.filter((branch) => branch.city === city) : branches;
  const cities = [...new Set(branches.map((branch) => branch.city))].sort();

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Help</h1>
          <p className="muted">
            For documents, timings, part-payment and more, ask the assistant. Here you can find a
            branch or ask us to call you.
          </p>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="card">
        <h2>Complaint or callback</h2>
        <form onSubmit={raise} noValidate>
          <label htmlFor="kind">What do you need?</label>
          <select id="kind" value={kind} onChange={(event) => setKind(event.target.value)}>
            {Object.entries(KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <label htmlFor="message">What is it about?</label>
          <textarea
            id="message"
            rows={3}
            maxLength={1000}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
          {kind === "callback" && (
            <>
              <label htmlFor="preferred">When should we call? (optional)</label>
              <input
                id="preferred"
                maxLength={60}
                placeholder="e.g. after 4 pm"
                value={preferredTime}
                onChange={(event) => setPreferredTime(event.target.value)}
              />
            </>
          )}
          <label htmlFor="ticket-branch">Branch</label>
          <select
            id="ticket-branch"
            value={branchId}
            onChange={(event) => setBranchId(event.target.value)}
          >
            <option value="">The branch of my loan</option>
            {branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
          </select>
          <p className="hint">Never write an account number, OTP or PIN here.</p>
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? "Sending…" : "Send"}
          </button>
        </form>
        {raised && (
          <p className="success" role="status">
            Sent. Your reference is <strong>{raised.reference}</strong>.
          </p>
        )}
      </section>

      {tickets.length > 0 && (
        <section>
          <h2>My requests</h2>
          <ul className="list">
            {tickets.map((ticket) => (
              <li key={ticket.id} className="card row">
                <div>
                  <strong>
                    {KINDS[ticket.kind]} · {ticket.reference}
                  </strong>
                  <p className="muted">
                    {formatDate(ticket.created_at)} · {ticket.message}
                  </p>
                </div>
                <span className={`status ${ticket.status}`}>{TICKET_STATUS[ticket.status]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <div className="section-header">
          <h2>Find a branch</h2>
          <div>
            <label htmlFor="branch-city" className="visually-hidden">
              City
            </label>
            <select id="branch-city" value={city} onChange={(event) => setCity(event.target.value)}>
              <option value="">All cities</option>
              {cities.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </div>
        </div>
        <ul className="list">
          {shown.map((branch) => (
            <li key={branch.id} className="card">
              <strong>{branch.name}</strong>
              <p className="muted">
                {branch.address}, {branch.city} {branch.pincode}
              </p>
              <p className="muted">
                {branch.timings} · {branch.phone}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
