import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import api from "../api";
import AdminDashboard from "../pages/AdminDashboard";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), put: vi.fn() },
}));

// jsdom has no layout, so give the charts a size to draw at
vi.mock("recharts", async (importOriginal) => {
  const recharts = await importOriginal();
  const { cloneElement } = await import("react");
  return {
    ...recharts,
    ResponsiveContainer: ({ children }) => cloneElement(children, { width: 600, height: 300 }),
  };
});

const STATS = {
  branches: [
    {
      branch_id: "b1",
      name: "Kochi MG Road (demo)",
      city: "Kochi",
      booked: 3,
      arrived: 1,
      valued: 2,
      no_show: 0,
      cancelled: 0,
      open_tickets: 1,
    },
  ],
  customers: 5,
  active_loans: 4,
  period_days: 7,
  estimates: 8,
  leads: 2,
  lead_conversion: 0.25,
};

const ANALYTICS = {
  turns: 10,
  pipelines: {
    cascade: { turns: 4, stages: { ttfa_ms: { n: 4, p50: 1800, p95: 2600 } } },
    text: { turns: 6, stages: { total_ms: { n: 6, p50: 900, p95: 1500 } } },
  },
  intents: { calculator: 6, account: 4 },
  languages: { hi: 5, ml: 3, en: 2 },
  answered_by: { gemini: 8, rules: 2 },
  primary_rate: 0.8,
  cache_rate: 0,
  fallback_rate: 0.2,
  barged_in: 1,
  guardrails: { shares_secret: 2 },
};

const VOICE = {
  stt_requests: 4,
  stt_seconds: 12.5,
  tts_requests: 9,
  tts_chars: 1200,
  tts_cache_hits: 3,
  caps: { stt_seconds: 18000, tts_chars: 200000 },
  out_of_credit: false,
};

function mockLoad() {
  api.get.mockImplementation(async (url) => {
    if (url === "/api/admin/stats") return { data: STATS };
    if (url === "/api/admin/analytics") return { data: ANALYTICS };
    if (url === "/api/admin/voice-usage") return { data: VOICE };
    return { data: { day: "2026-11-06", rate_per_gram: { 24: 12500, 22: 11458, 18: 9375 } } };
  });
}

beforeEach(() => vi.clearAllMocks());

test("leads, conversion and branch activity", async () => {
  mockLoad();
  render(<AdminDashboard />);

  expect(await screen.findByText("Loan estimates given")).toBeInTheDocument();
  expect(screen.getByText("25%")).toBeInTheDocument();
  expect(screen.getByText("Kochi MG Road (demo)")).toBeInTheDocument();
});

test("languages and intents are named, and guardrail activity is listed", async () => {
  mockLoad();
  render(<AdminDashboard />);

  expect(await screen.findByRole("img", { name: "Language of each turn" })).toBeInTheDocument();
  expect(screen.getByText("Malayalam")).toBeInTheDocument();
  expect(screen.getByText("Loan estimate")).toBeInTheDocument();
  expect(screen.getByText(/tried to share an OTP/)).toHaveTextContent("2");
  expect(screen.getByRole("cell", { name: "Time to first audio" })).toBeInTheDocument();
});

test("voice credit use is shown against the caps", async () => {
  mockLoad();
  render(<AdminDashboard />);

  expect(await screen.findByText(/1200 characters of 200000 allowed/)).toBeInTheDocument();
  expect(screen.getByText(/3 sentences replayed/)).toBeInTheDocument();
});

test("the admin sets today's gold rate", async () => {
  const user = userEvent.setup();
  mockLoad();
  api.put.mockResolvedValue({ data: { rate_per_gram: { 24: 13000, 22: 11917, 18: 9750 } } });
  render(<AdminDashboard />);

  await user.type(await screen.findByLabelText("Today's 24 carat rate (₹ per gram)"), "13000");
  await user.click(screen.getByRole("button", { name: "Save rate" }));

  expect(api.put).toHaveBeenCalledWith("/api/gold/rate", { rate_24k_per_gram: 13000 });
  expect(await screen.findByRole("status")).toHaveTextContent("₹11,917/g");
});
