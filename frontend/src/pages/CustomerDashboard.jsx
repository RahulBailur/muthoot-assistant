import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import api, { errorMessage } from "../api";
import { ACCOUNT_CHANGED } from "../components/Assistant";
import { useAuth } from "../context/AuthContext";
import { VISIT_EVENT, useLiveUpdates } from "../context/LiveUpdatesContext";
import { formatDay, rupees } from "../format";
import { formatDate, formatTime } from "../time";

const URGENT = ["auction_warning", "auction_notice_due", "interest_overdue"];

const VISIT_STATUS = {
  booked: "Booked",
  arrived: "At the branch",
  valued: "Valuation done",
  no_show: "Missed",
  cancelled: "Cancelled",
};

function Reminder({ reminder }) {
  return (
    <p className={`notice ${URGENT.includes(reminder.kind) ? "warning" : ""}`}>
      {URGENT.includes(reminder.kind) && <strong>Important: </strong>}
      {reminder.message}
    </p>
  );
}

function LoanCard({ loan }) {
  const active = loan.status === "active";
  return (
    <li className="card">
      <header className="card-header">
        <div>
          <h3>Loan ending {loan.account_last4}</h3>
          <p className="muted">
            {loan.scheme} scheme · {loan.gold_weight_grams} g of {loan.purity_carat} carat ·{" "}
            {loan.interest_rate_pa}% a year
          </p>
        </div>
        <span className={`status ${loan.status}`}>{active ? "Active" : "Closed"}</span>
      </header>
      {active ? (
        <>
          <div className="stats">
            <div className="stat">
              <p className="stat-label">Outstanding</p>
              <p className="stat-value">{rupees(loan.outstanding)}</p>
            </div>
            <div className="stat">
              <p className="stat-label">Interest due</p>
              <p className="stat-value">{rupees(loan.interest_due)}</p>
              <p className="stat-note">by {formatDay(loan.next_due_date)}</p>
            </div>
            <div className="stat">
              <p className="stat-label">Matures</p>
              <p className="stat-value">{formatDay(loan.maturity_date)}</p>
            </div>
            {loan.top_up_available > 0 && (
              <div className="stat">
                <p className="stat-label">Top-up possible</p>
                <p className="stat-value">up to {rupees(loan.top_up_available)}</p>
                <p className="stat-note">estimate at today's rate, decided at valuation</p>
              </div>
            )}
          </div>
          {loan.reminders.map((reminder) => (
            <Reminder key={reminder.kind} reminder={reminder} />
          ))}
        </>
      ) : (
        <p className="muted">This loan is closed.</p>
      )}
    </li>
  );
}

export default function CustomerDashboard() {
  const { user } = useAuth();
  const [loans, setLoans] = useState(null);
  const [visits, setVisits] = useState([]);
  const [rate, setRate] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [loanList, visitList, todayRate] = await Promise.all([
        api.get("/api/loans/me"),
        api.get("/api/visits/me"),
        api.get("/api/gold/rate"),
      ]);
      setLoans(loanList.data);
      setVisits(visitList.data);
      setRate(todayRate.data);
      setError("");
    } catch (err) {
      setError(errorMessage(err, "Could not load your loans."));
    }
  }, []);

  useEffect(() => {
    load();
    // A visit booked or cancelled through the assistant shows up here at once
    window.addEventListener(ACCOUNT_CHANGED, load);
    return () => window.removeEventListener(ACCOUNT_CHANGED, load);
  }, [load]);

  // Branch staff marking the customer arrived, or the valuation done, shows up live
  useLiveUpdates(VISIT_EVENT, (update) =>
    setVisits((current) => current.map((visit) => (visit.id === update.id ? update : visit))),
  );

  async function cancel(visit) {
    try {
      await api.post(`/api/visits/${visit.id}/cancel`);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Could not cancel the visit."));
    }
  }

  const upcoming = visits.filter((visit) => ["booked", "arrived"].includes(visit.status));

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Hello, {user.name}</h1>
          <p className="muted">Logged in as {user.phone_masked}</p>
        </div>
        {rate && (
          <div className="stat">
            <p className="stat-label">Today's gold rate (22 carat)</p>
            <p className="stat-value">{rupees(rate.rate_per_gram["22"])}/g</p>
            <p className="stat-note">24 carat {rupees(rate.rate_per_gram["24"])}/g</p>
          </div>
        )}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section>
        <div className="section-header">
          <h2>My gold loans</h2>
          <Link to="/estimate" className="button">
            Estimate a new loan
          </Link>
        </div>
        {loans === null && !error && <p className="muted">Loading…</p>}
        {loans?.length === 0 && (
          <p className="muted">
            You have no gold loans with us yet.{" "}
            <Link to="/estimate">See how much you could get</Link>.
          </p>
        )}
        <ul className="list">
          {loans?.map((loan) => (
            <LoanCard key={loan.id} loan={loan} />
          ))}
        </ul>
      </section>

      <section>
        <div className="section-header">
          <h2>Branch visits</h2>
          <Link to="/book" className="button">
            Book a visit
          </Link>
        </div>
        {upcoming.length === 0 && <p className="muted">No upcoming visits.</p>}
        <ul className="list">
          {upcoming.map((visit) => (
            <li key={visit.id} className="card row">
              <div>
                <strong>{visit.branch_name}</strong>
                <p className="muted">
                  {formatDate(visit.slot_start)}, {formatTime(visit.slot_start)} · gold valuation
                </p>
              </div>
              <div className="actions">
                <span className={`status ${visit.status}`}>{VISIT_STATUS[visit.status]}</span>
                {visit.status === "booked" && (
                  <button type="button" className="button quiet" onClick={() => cancel(visit)}>
                    Cancel
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
