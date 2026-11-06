import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api, { errorMessage } from "../api";
import { rupees } from "../format";

export const PIPELINE_NAMES = { cascade: "Voice", text: "Text chat" };

export const STAGE_NAMES = {
  end_of_speech_ms: "End-of-speech detection",
  stt_ms: "Speech to text",
  routing_ms: "Routing",
  llm_ms: "Assistant (model and tools)",
  tts_first_chunk_ms: "Speech, first sentence",
  ttfa_ms: "Time to first audio",
  total_ms: "Whole turn",
};

const INTENT_NAMES = {
  calculator: "Loan estimate",
  visit: "Branch visit",
  account: "My loan account",
  help: "Help and FAQ",
  general: "Greetings and other",
};

export const LANGUAGE_NAMES = {
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
  ml: "Malayalam",
  ta: "Tamil",
};

const TIER_NAMES = {
  gemini: "Gemini",
  ollama: "Ollama (local)",
  cache: "Response cache",
  rules: "Rule-based reply",
  guardrail: "Guardrail reply",
  unknown: "Not recorded",
};

const GUARDRAIL_NAMES = {
  shares_secret: "Customer tried to share an OTP or PIN",
  investment_question: "Investment advice refused",
  asks_for_secret: "Reply asked for a secret (blocked)",
  promise: "Reply promised a loan (blocked)",
  investment_advice: "Reply gave investment advice (blocked)",
};

const PIPELINE_ORDER = ["cascade", "text"];
const STAGE_ORDER = Object.keys(STAGE_NAMES);
const byOrder = (order) => (a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99);

const WINDOWS = [
  { days: 1, label: "Last 24 hours" },
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
];

const seconds = (ms) => `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
const percent = (share) => `${Math.round(share * 100)}%`;

function Stat({ label, value, note }) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="stat-note">{note}</p>}
    </div>
  );
}

/** Recharts' tooltip, in the page's own colours. */
const tooltipProps = {
  cursor: { fill: "var(--accent-soft)" },
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    color: "var(--text)",
  },
  labelStyle: { color: "var(--text)", fontWeight: 600 },
  itemStyle: { color: "var(--text)" },
};

const axisProps = {
  stroke: "var(--border)",
  tick: { fill: "var(--muted)", fontSize: 12 },
  tickLine: false,
};

/** How long a customer waits for the answer to start: first audio by voice, the reply in chat. */
function LatencyChart({ pipelines }) {
  const rows = [
    ["cascade", "ttfa_ms", "Voice: first audio"],
    ["text", "total_ms", "Text: reply"],
  ]
    .filter(([name, stage]) => pipelines[name]?.stages?.[stage])
    .map(([name, stage, label]) => ({
      name: label,
      p50: pipelines[name].stages[stage].p50 / 1000,
      p95: pipelines[name].stages[stage].p95 / 1000,
    }));
  if (rows.length === 0) return <p className="muted">No conversations in this period yet.</p>;
  return (
    <div className="chart" role="img" aria-label="How long customers wait for an answer">
      <ResponsiveContainer width="100%" height={60 + rows.length * 70}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 56 }} barGap={2}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" unit=" s" {...axisProps} />
          <YAxis type="category" dataKey="name" width={150} {...axisProps} />
          <Tooltip {...tooltipProps} formatter={(value) => `${value.toFixed(2)} s`} />
          {/* The swatch carries the colour; the words stay in text colour */}
          <Legend
            wrapperStyle={{ fontSize: 13 }}
            formatter={(value) => <span style={{ color: "var(--muted)" }}>{value}</span>}
          />
          {[
            ["p50", "Median (P50)", "var(--series-1)"],
            ["p95", "Slow turns (P95)", "var(--series-2)"],
          ].map(([key, name, colour]) => (
            <Bar
              key={key}
              dataKey={key}
              name={name}
              fill={colour}
              barSize={16}
              radius={[0, 4, 4, 0]}
            >
              <LabelList
                dataKey={key}
                position="right"
                formatter={(value) => `${value.toFixed(1)} s`}
                style={{ fill: "var(--muted)", fontSize: 12 }}
              />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** One measure, a few categories: a single-series bar chart with the share at each tip. */
function CountChart({ label, counts, names = {} }) {
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const rows = Object.entries(counts).map(([key, count]) => ({
    name: names[key] ?? key,
    count,
    share: total ? count / total : 0,
  }));
  if (rows.length === 0) return <p className="muted">Nothing yet.</p>;
  return (
    <div className="chart" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={30 + rows.length * 36}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 48 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" allowDecimals={false} {...axisProps} />
          <YAxis type="category" dataKey="name" width={140} {...axisProps} />
          <Tooltip
            {...tooltipProps}
            formatter={(value, _, item) => [`${value} (${percent(item.payload.share)})`, "Turns"]}
          />
          <Bar dataKey="count" fill="var(--series-1)" barSize={16} radius={[0, 4, 4, 0]}>
            <LabelList
              dataKey="share"
              position="right"
              formatter={percent}
              style={{ fill: "var(--muted)", fontSize: 12 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StageTable({ pipelines }) {
  const names = Object.keys(pipelines).sort(byOrder(PIPELINE_ORDER));
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">Latency per stage</caption>
        <thead>
          <tr>
            <th scope="col">Channel</th>
            <th scope="col">Stage</th>
            <th scope="col">P50</th>
            <th scope="col">P95</th>
            <th scope="col">Turns</th>
          </tr>
        </thead>
        <tbody>
          {names.flatMap((pipeline) =>
            Object.entries(pipelines[pipeline].stages)
              .sort(([a], [b]) => byOrder(STAGE_ORDER)(a, b))
              .map(([stage, stats]) => (
                <tr key={`${pipeline}-${stage}`}>
                  <td>{PIPELINE_NAMES[pipeline] ?? pipeline}</td>
                  <td>{STAGE_NAMES[stage] ?? stage}</td>
                  <td>{seconds(stats.p50)}</td>
                  <td>{seconds(stats.p95)}</td>
                  <td>{stats.n}</td>
                </tr>
              )),
          )}
        </tbody>
      </table>
    </div>
  );
}

function BranchTable({ branches }) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">Branch activity today</caption>
        <thead>
          <tr>
            <th scope="col">Branch</th>
            <th scope="col">Booked</th>
            <th scope="col">Waiting</th>
            <th scope="col">Valued</th>
            <th scope="col">No-show</th>
            <th scope="col">Open callbacks and complaints</th>
          </tr>
        </thead>
        <tbody>
          {branches.map((row) => (
            <tr key={row.branch_id}>
              <td>{row.name}</td>
              <td>{row.booked}</td>
              <td>{row.arrived}</td>
              <td>{row.valued}</td>
              <td>{row.no_show}</td>
              <td>{row.open_tickets}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GoldRateForm({ onSaved }) {
  const [rate, setRate] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function save(event) {
    event.preventDefault();
    setNote("");
    setError("");
    const value = Number(rate);
    if (!Number.isInteger(value) || value <= 1000 || value >= 100000) {
      setError("Enter the 24 carat rate per gram in whole rupees.");
      return;
    }
    try {
      const { data } = await api.put("/api/gold/rate", { rate_24k_per_gram: value });
      setRate("");
      setNote(`Saved. 22 carat is now ${rupees(data.rate_per_gram["22"])}/g.`);
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the rate."));
    }
  }

  return (
    <form className="inline-form" onSubmit={save} noValidate>
      <label htmlFor="rate">Today's 24 carat rate (₹ per gram)</label>
      <input
        id="rate"
        type="number"
        inputMode="numeric"
        value={rate}
        onChange={(event) => setRate(event.target.value)}
      />
      <button type="submit" className="button">
        Save rate
      </button>
      {note && (
        <p className="success" role="status">
          {note}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

/** Admin: leads and branch activity, how the assistant is doing, and voice credit use. */
export default function AdminDashboard() {
  const [days, setDays] = useState(7);
  const [stats, setStats] = useState(null);
  const [assistant, setAssistant] = useState(null);
  const [voice, setVoice] = useState(null);
  const [rate, setRate] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [business, summary, usage, todayRate] = await Promise.all([
        api.get("/api/admin/stats", { params: { days } }),
        api.get("/api/admin/analytics", { params: { days } }),
        api.get("/api/admin/voice-usage"),
        api.get("/api/gold/rate"),
      ]);
      setStats(business.data);
      setAssistant(summary.data);
      setVoice(usage.data);
      setRate(todayRate.data);
      setError("");
    } catch (err) {
      setError(errorMessage(err, "Could not load the analytics."));
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div className="page-header">
        <h1>Analytics</h1>
        <div className="actions">
          <label className="inline-label">
            <span className="visually-hidden">Period</span>
            <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
              {WINDOWS.map((window) => (
                <option key={window.days} value={window.days}>
                  {window.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="button" onClick={load}>
            Refresh
          </button>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!stats && !error && <p className="muted">Loading…</p>}

      {stats && (
        <section aria-labelledby="leads-heading">
          <h2 id="leads-heading">Leads</h2>
          <div className="stats">
            <Stat label="Loan estimates given" value={stats.estimates} />
            <Stat label="Leads" value={stats.leads} note="branch visits booked after an estimate" />
            <Stat label="Estimate to visit" value={percent(stats.lead_conversion)} />
            <Stat label="Customers" value={stats.customers} />
            <Stat label="Active loans" value={stats.active_loans} />
          </div>
          <h3>Branches today</h3>
          <BranchTable branches={stats.branches} />
        </section>
      )}

      {assistant && (
        <section aria-labelledby="assistant-heading">
          <h2 id="assistant-heading">The assistant</h2>
          {assistant.turns === 0 ? (
            <p className="muted">No conversations in this period yet.</p>
          ) : (
            <>
              <div className="stats">
                <Stat label="Turns" value={assistant.turns} />
                <Stat label="Answered by Gemini" value={percent(assistant.primary_rate)} />
                <Stat label="From the response cache" value={percent(assistant.cache_rate)} />
                <Stat
                  label="Needed a fallback"
                  value={percent(assistant.fallback_rate)}
                  note="Ollama or a rule-based reply"
                />
                <Stat label="Interrupted by the customer" value={assistant.barged_in} />
              </div>

              <div className="chart-grid">
                <div>
                  <h3>What customers asked about</h3>
                  <CountChart
                    label="Intent of each turn"
                    counts={assistant.intents}
                    names={INTENT_NAMES}
                  />
                </div>
                <div>
                  <h3>Languages</h3>
                  <CountChart
                    label="Language of each turn"
                    counts={assistant.languages}
                    names={LANGUAGE_NAMES}
                  />
                </div>
              </div>

              <h3>How long customers wait</h3>
              <p className="muted">
                By voice, from the moment the customer stops speaking to the first sound of the
                reply.
              </p>
              <LatencyChart pipelines={assistant.pipelines} />
              <h3>Latency by stage</h3>
              <StageTable pipelines={assistant.pipelines} />

              <div className="chart-grid">
                <div>
                  <h3>Who answered</h3>
                  <CountChart
                    label="Which tier answered each turn"
                    counts={assistant.answered_by}
                    names={TIER_NAMES}
                  />
                </div>
                <div>
                  <h3>Guardrails</h3>
                  {Object.keys(assistant.guardrails).length === 0 ? (
                    <p className="muted">None triggered in this period.</p>
                  ) : (
                    <ul className="list">
                      {Object.entries(assistant.guardrails).map(([kind, count]) => (
                        <li key={kind}>
                          {GUARDRAIL_NAMES[kind] ?? kind}: <strong>{count}</strong>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      )}

      <section aria-labelledby="settings-heading">
        <h2 id="settings-heading">Gold rate and voice credits</h2>
        <div className="chart-grid">
          <div className="card">
            {rate && (
              <p>
                Today: <strong>{rupees(rate.rate_per_gram["24"])}/g</strong> for 24 carat,{" "}
                {rupees(rate.rate_per_gram["22"])}/g for 22 carat.
              </p>
            )}
            <GoldRateForm onSaved={load} />
          </div>
          {voice && (
            <div className="card">
              <p>
                Speech to text: <strong>{voice.stt_requests}</strong> requests, {voice.stt_seconds}{" "}
                s{voice.caps.stt_seconds && ` of ${voice.caps.stt_seconds} s allowed`}
              </p>
              <p>
                Text to speech: <strong>{voice.tts_requests}</strong> requests, {voice.tts_chars}{" "}
                characters
                {voice.caps.tts_chars && ` of ${voice.caps.tts_chars} allowed`}
              </p>
              <p className="muted">
                {voice.tts_cache_hits} sentences replayed from memory at no cost.
              </p>
              {voice.out_of_credit && (
                <p className="notice warning">
                  The speech provider reports no credit left. Voice replies are shown as text.
                </p>
              )}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
