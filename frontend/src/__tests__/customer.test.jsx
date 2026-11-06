import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import api from "../api";
import { rupees } from "../format";
import CustomerDashboard from "../pages/CustomerDashboard";
import LoanCalculator from "../pages/LoanCalculator";

const live = vi.hoisted(() => ({ push: null }));

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../context/LiveUpdatesContext", () => ({
  VISIT_EVENT: "visit:update",
  useLiveUpdates: (event, handler) => {
    live.push = handler;
    return { connected: true };
  },
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { name: "Lakshmi", phone_masked: "******0201", role: "customer" } }),
}));

beforeEach(() => vi.clearAllMocks());

const ESTIMATE = {
  grams: 30,
  carat: 22,
  rate_per_gram: 11000,
  gold_value: 330000,
  ltv_limit: 0.75,
  low: 222700,
  high: 247500,
  schemes: [
    {
      code: "saver",
      name: "Saver",
      interest_rate_pa: 12,
      repayment: "Pay interest every month",
      monthly_interest_low: 2227,
      monthly_interest_high: 2475,
    },
  ],
  disclaimer: "This is an estimate only. The final loan amount is decided after valuation.",
};

test("amounts use Indian digit grouping", () => {
  expect(rupees(247500)).toBe("₹2,47,500");
});

describe("loan calculator", () => {
  function renderCalculator() {
    return render(
      <MemoryRouter>
        <LoanCalculator />
      </MemoryRouter>,
    );
  }

  test("shows a range, never one figure, with the disclaimer", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ data: ESTIMATE });
    renderCalculator();

    await user.type(screen.getByLabelText("Weight of your gold"), "30");
    await user.click(screen.getByRole("button", { name: "Estimate" }));

    expect(await screen.findByText("About ₹2,22,700 to ₹2,47,500")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("estimate only");
    expect(screen.getByText("₹2,227 to ₹2,475")).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/api/gold/estimate", { grams: 30, carat: 22 });
  });

  test("pavan are turned into grams", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ data: ESTIMATE });
    renderCalculator();

    await user.type(screen.getByLabelText("Weight of your gold"), "4");
    await user.selectOptions(screen.getByLabelText("Unit"), "pavan");
    await user.selectOptions(screen.getByLabelText("Purity"), "24");
    await user.click(screen.getByRole("button", { name: "Estimate" }));

    expect(api.post).toHaveBeenCalledWith("/api/gold/estimate", { grams: 32, carat: 24 });
  });

  test("an empty weight is caught before asking the server", async () => {
    const user = userEvent.setup();
    renderCalculator();

    await user.click(screen.getByRole("button", { name: "Estimate" }));

    expect(screen.getByRole("alert")).toHaveTextContent("between 1 and 1000 grams");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("customer dashboard", () => {
  const LOAN = {
    id: "l1",
    account_masked: "XXXXXXXX0004",
    account_last4: "0004",
    scheme: "Bullet",
    principal: 70000,
    outstanding: 70000,
    interest_rate_pa: 18,
    interest_due: 1050,
    gold_weight_grams: 15,
    purity_carat: 18,
    opened_on: "2025-10-27",
    next_due_date: "2026-10-27",
    maturity_date: "2026-10-27",
    status: "active",
    top_up_available: 35400,
    reminders: [
      {
        kind: "auction_warning",
        message: "Your loan has matured. Renew or close it within 20 days.",
        days: 20,
      },
    ],
  };
  const VISIT = {
    id: "v1",
    branch_name: "Kochi MG Road (demo)",
    slot_start: "2026-11-07T04:00:00Z",
    slot_end: "2026-11-07T04:30:00Z",
    status: "booked",
  };

  function mockLoad() {
    api.get.mockImplementation(async (url) => {
      if (url === "/api/loans/me") return { data: [LOAN] };
      if (url === "/api/visits/me") return { data: [VISIT] };
      return { data: { day: "2026-11-06", rate_per_gram: { 24: 12500, 22: 11458, 18: 9375 } } };
    });
  }

  function renderDashboard() {
    return render(
      <MemoryRouter>
        <CustomerDashboard />
      </MemoryRouter>,
    );
  }

  test("a loan is named by its last four digits only, with its reminders", async () => {
    mockLoad();
    renderDashboard();

    expect(await screen.findByText("Loan ending 0004")).toBeInTheDocument();
    expect(screen.queryByText(/XXXXXXXX0004/)).not.toBeInTheDocument();
    expect(screen.getByText(/within 20 days/)).toHaveTextContent("Important:");
    expect(screen.getByText("up to ₹35,400")).toBeInTheDocument();
    expect(screen.getByText("₹11,458/g")).toBeInTheDocument();
  });

  test("a visit moves to 'at the branch' live when staff mark it", async () => {
    mockLoad();
    renderDashboard();
    await screen.findByText("Kochi MG Road (demo)");

    act(() => live.push({ ...VISIT, status: "arrived" }));

    expect(screen.getByText("At the branch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });
});
