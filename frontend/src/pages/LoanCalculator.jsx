import { useState } from "react";
import { Link } from "react-router-dom";

import api, { errorMessage } from "../api";
import EstimateDisclaimer from "../components/EstimateDisclaimer";
import { rupees } from "../format";

const PAVAN_GRAMS = 8;

/** The headline use case without the assistant: weight and purity in, a loan range out. */
export default function LoanCalculator() {
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("grams");
  const [carat, setCarat] = useState("22");
  const [estimate, setEstimate] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    const number = Number(amount);
    const grams = unit === "pavan" ? number * PAVAN_GRAMS : number;
    if (!(grams > 0 && grams <= 1000)) {
      setError("Enter a weight between 1 and 1000 grams.");
      return;
    }
    setBusy(true);
    try {
      setEstimate((await api.post("/api/gold/estimate", { grams, carat: Number(carat) })).data);
    } catch (err) {
      setError(errorMessage(err, "Could not work out the estimate."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>How much can I get?</h1>
          <p className="muted">An estimate at today's gold rate. You can also ask the assistant.</p>
        </div>
      </div>

      <form className="card form-row" onSubmit={handleSubmit} noValidate>
        <div>
          <label htmlFor="weight">Weight of your gold</label>
          <input
            id="weight"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.1"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="unit">Unit</label>
          <select id="unit" value={unit} onChange={(event) => setUnit(event.target.value)}>
            <option value="grams">grams</option>
            <option value="pavan">pavan (8 g)</option>
          </select>
        </div>
        <div>
          <label htmlFor="carat">Purity</label>
          <select id="carat" value={carat} onChange={(event) => setCarat(event.target.value)}>
            <option value="22">22 carat (most jewellery)</option>
            <option value="24">24 carat</option>
            <option value="18">18 carat</option>
          </select>
        </div>
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? "Working it out…" : "Estimate"}
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {estimate && (
        <section className="card" aria-live="polite">
          <p className="muted">
            {estimate.grams} g of {estimate.carat} carat gold at {rupees(estimate.rate_per_gram)}/g
            is worth about {rupees(estimate.gold_value)}. You can borrow up to{" "}
            {Math.round(estimate.ltv_limit * 100)}% of that.
          </p>
          <p className="queue-position">
            About {rupees(estimate.low)} to {rupees(estimate.high)}
          </p>
          <EstimateDisclaimer text={estimate.disclaimer} />

          <h2>Interest schemes</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Scheme</th>
                  <th scope="col">Interest</th>
                  <th scope="col">Repayment</th>
                  <th scope="col">Interest a month</th>
                </tr>
              </thead>
              <tbody>
                {estimate.schemes.map((scheme) => (
                  <tr key={scheme.code}>
                    <td>{scheme.name}</td>
                    <td>{scheme.interest_rate_pa}% a year</td>
                    <td>{scheme.repayment}</td>
                    <td>
                      {rupees(scheme.monthly_interest_low)} to{" "}
                      {rupees(scheme.monthly_interest_high)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            <Link to="/book" className="button primary">
              Book a branch visit to value your gold
            </Link>
          </p>
        </section>
      )}
    </>
  );
}
