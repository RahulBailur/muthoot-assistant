import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api, { errorMessage } from "../api";
import { addDaysIso, formatDate, formatTime, todayIso } from "../time";

const BOOKING_WINDOW_DAYS = 14;
const PURPOSES = {
  new_loan: "New gold loan",
  renewal: "Renew my loan",
  top_up: "Top-up",
  close_loan: "Close my loan",
};

/** Book a gold valuation slot: city, day, slot, then a confirmation before anything is booked. */
export default function BookVisit() {
  const [branches, setBranches] = useState([]);
  const [city, setCity] = useState("");
  const [day, setDay] = useState(todayIso());
  const [purpose, setPurpose] = useState("new_loan");
  const [found, setFound] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [booked, setBooked] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/api/branches")
      .then((response) => setBranches(response.data))
      .catch((err) => setError(errorMessage(err, "Could not load the branches.")));
  }, []);

  const cities = useMemo(() => [...new Set(branches.map((b) => b.city))].sort(), [branches]);

  useEffect(() => {
    if (!city) return;
    let cancelled = false;
    setChosen(null);
    api
      .get("/api/visits/availability", { params: { city, date: day } })
      .then((response) => !cancelled && setFound(response.data))
      .catch((err) => !cancelled && setError(errorMessage(err, "Could not load the slots.")));
    return () => {
      cancelled = true;
    };
  }, [city, day]);

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/api/visits/book", {
        branch_id: chosen.branch.branch_id,
        slot_start: chosen.slot.start,
        purpose,
      });
      setBooked(data);
    } catch (err) {
      setError(errorMessage(err, "Could not book that slot."));
      setChosen(null);
    } finally {
      setBusy(false);
    }
  }

  if (booked) {
    return (
      <section className="card">
        <h1>Visit booked</h1>
        <p className="success" role="status">
          {booked.branch_name}, {formatDate(booked.slot_start)} at {formatTime(booked.slot_start)}.
        </p>
        <p className="muted">
          Bring your gold, one photo ID and one address proof. The final loan amount is decided
          after valuation at the branch.
        </p>
        <Link to="/" className="button primary">
          Back to my loans
        </Link>
      </section>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Book a branch visit</h1>
          <p className="muted">A free gold valuation slot of 30 minutes.</p>
        </div>
      </div>

      <div className="card form-row">
        <div>
          <label htmlFor="city">City</label>
          <select id="city" value={city} onChange={(event) => setCity(event.target.value)}>
            <option value="">Choose a city</option>
            {cities.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="day">Date</label>
          <input
            id="day"
            type="date"
            min={todayIso()}
            max={addDaysIso(todayIso(), BOOKING_WINDOW_DAYS)}
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="purpose">Why are you coming?</label>
          <select id="purpose" value={purpose} onChange={(event) => setPurpose(event.target.value)}>
            {Object.entries(PURPOSES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {found?.map((branch) => (
        <section key={branch.branch_id} className="card">
          <h2>{branch.branch_name}</h2>
          {branch.slots.length === 0 ? (
            <p className="muted">No free slots on this day.</p>
          ) : (
            <div className="slots">
              {branch.slots.map((slot) => (
                <button
                  key={slot.start}
                  type="button"
                  className={`slot ${chosen?.slot.start === slot.start ? "selected" : ""}`}
                  aria-pressed={chosen?.slot.start === slot.start}
                  onClick={() => setChosen({ branch, slot })}
                >
                  {formatTime(slot.start)}
                </button>
              ))}
            </div>
          )}
        </section>
      ))}

      {chosen && (
        <div className="card confirm" role="dialog" aria-label="Confirm booking">
          <p>
            Book <strong>{chosen.branch.branch_name}</strong> on {formatDate(chosen.slot.start)} at{" "}
            {formatTime(chosen.slot.start)} ({PURPOSES[purpose].toLowerCase()})?
          </p>
          <div className="actions">
            <button type="button" className="button primary" disabled={busy} onClick={confirm}>
              {busy ? "Booking…" : "Yes, book it"}
            </button>
            <button type="button" className="button quiet" onClick={() => setChosen(null)}>
              No, go back
            </button>
          </div>
        </div>
      )}
    </>
  );
}
