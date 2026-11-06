import { useCallback, useEffect, useState } from "react";

import api, { errorMessage } from "../api";
import { useAuth } from "../context/AuthContext";
import { BRANCH_EVENT, useLiveUpdates } from "../context/LiveUpdatesContext";
import { formatTime } from "../time";

const VISIT_STATUS = {
  booked: "Booked",
  arrived: "Waiting",
  valued: "Valued",
  no_show: "No-show",
};

// The buttons staff get for a visit in each state
const NEXT_ACTIONS = {
  booked: [
    { status: "arrived", label: "Customer arrived", style: "primary" },
    { status: "no_show", label: "No-show", style: "quiet" },
  ],
  arrived: [{ status: "valued", label: "Valuation done", style: "primary" }],
};

const TICKET_ACTIONS = {
  open: [
    { status: "in_progress", label: "Calling now", style: "quiet" },
    { status: "resolved", label: "Resolved", style: "primary" },
  ],
  in_progress: [{ status: "resolved", label: "Resolved", style: "primary" }],
};

const KINDS = { callback: "Callback", complaint: "Complaint" };

function VisitRow({ visit, position, onStatus }) {
  return (
    <li className="card row">
      <div>
        <strong>
          {position && <span className="queue-number">#{position}</span>} {visit.customer_name}
        </strong>
        <p className="muted">
          {visit.is_walk_in ? "Walk-in" : `Booked for ${formatTime(visit.slot_start)}`}
          {visit.arrived_at && ` · arrived ${formatTime(visit.arrived_at)}`}
          {visit.customer_phone_masked && ` · ${visit.customer_phone_masked}`}
          {visit.is_lead && " · came from a loan estimate"}
        </p>
      </div>
      <div className="actions">
        <span className={`status ${visit.status}`}>{VISIT_STATUS[visit.status]}</span>
        {(NEXT_ACTIONS[visit.status] ?? []).map((action) => (
          <button
            key={action.status}
            type="button"
            className={`button ${action.style}`}
            onClick={() => onStatus(visit, action.status)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </li>
  );
}

/** The branch's day, live: who is waiting, who is booked, and who asked for a call. */
export default function BranchQueue() {
  const { user } = useAuth();
  const [visits, setVisits] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [walkIn, setWalkIn] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [visitList, ticketList] = await Promise.all([
        api.get("/api/visits/branch"),
        api.get("/api/tickets/branch"),
      ]);
      setVisits(visitList.data);
      setTickets(ticketList.data);
      setError("");
    } catch (err) {
      setError(errorMessage(err, "Could not load the branch queue."));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Every change at the branch (a booking, a walk-in, a callback request) arrives here
  const { connected } = useLiveUpdates(BRANCH_EVENT, (update) => {
    setVisits(update.visits);
    setTickets(update.tickets);
  });

  async function setVisitStatus(visit, status) {
    try {
      await api.put(`/api/visits/${visit.id}/status`, { status });
      await load();
    } catch (err) {
      setError(errorMessage(err, "Could not update the visit."));
    }
  }

  async function setTicketStatus(ticket, status) {
    try {
      await api.put(`/api/tickets/${ticket.id}/status`, { status });
      await load();
    } catch (err) {
      setError(errorMessage(err, "Could not update the request."));
    }
  }

  async function addWalkIn(event) {
    event.preventDefault();
    const name = walkIn.trim();
    if (name.length < 2) {
      setError("Enter the customer's name.");
      return;
    }
    try {
      await api.post("/api/visits/walk-in", { name });
      setWalkIn("");
      await load();
    } catch (err) {
      setError(errorMessage(err, "Could not add the walk-in."));
    }
  }

  // Waiting customers in the order they arrived; the rest by booked time
  const waiting = (visits ?? [])
    .filter((visit) => visit.status === "arrived")
    .sort((a, b) => a.arrived_at.localeCompare(b.arrived_at));
  const booked = (visits ?? []).filter((visit) => visit.status === "booked");
  const finished = (visits ?? []).filter((visit) => ["valued", "no_show"].includes(visit.status));

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Today at the branch</h1>
          <p className="muted">{user.name}</p>
        </div>
        <span className={connected ? "live-dot on" : "live-dot"}>
          {connected ? "Live" : "Reconnecting…"}
        </span>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {visits === null && !error && <p className="muted">Loading…</p>}

      <section>
        <div className="section-header">
          <h2>
            Waiting for valuation <span className="muted">· {waiting.length}</span>
          </h2>
          <form className="inline-form" onSubmit={addWalkIn} noValidate>
            <label htmlFor="walk-in">Walk-in customer's name</label>
            <input
              id="walk-in"
              maxLength={80}
              value={walkIn}
              onChange={(event) => setWalkIn(event.target.value)}
            />
            <button type="submit" className="button">
              Add walk-in
            </button>
          </form>
        </div>
        {waiting.length === 0 && <p className="muted">Nobody is waiting.</p>}
        <ul className="list">
          {waiting.map((visit, index) => (
            <VisitRow key={visit.id} visit={visit} position={index + 1} onStatus={setVisitStatus} />
          ))}
        </ul>
      </section>

      <section>
        <h2>
          Booked today <span className="muted">· {booked.length}</span>
        </h2>
        {booked.length === 0 && <p className="muted">No more bookings today.</p>}
        <ul className="list">
          {booked.map((visit) => (
            <VisitRow key={visit.id} visit={visit} onStatus={setVisitStatus} />
          ))}
        </ul>
      </section>

      <section>
        <h2>
          Callbacks and complaints <span className="muted">· {tickets.length} open</span>
        </h2>
        {tickets.length === 0 && <p className="muted">Nothing open.</p>}
        <ul className="list">
          {tickets.map((ticket) => (
            <li key={ticket.id} className="card row">
              <div>
                <strong>
                  {KINDS[ticket.kind]} · {ticket.customer_name}
                </strong>
                <p className="muted">
                  {ticket.reference} · {ticket.customer_phone_masked}
                  {ticket.preferred_time && ` · call ${ticket.preferred_time}`}
                </p>
                <p>{ticket.message}</p>
              </div>
              <div className="actions">
                {(TICKET_ACTIONS[ticket.status] ?? []).map((action) => (
                  <button
                    key={action.status}
                    type="button"
                    className={`button ${action.style}`}
                    onClick={() => setTicketStatus(ticket, action.status)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {finished.length > 0 && (
        <section>
          <h2>
            Done today <span className="muted">· {finished.length}</span>
          </h2>
          <ul className="list">
            {finished.map((visit) => (
              <VisitRow key={visit.id} visit={visit} onStatus={setVisitStatus} />
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
