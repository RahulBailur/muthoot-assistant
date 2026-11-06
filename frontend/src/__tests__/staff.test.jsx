import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import api from "../api";
import BranchQueue from "../pages/BranchQueue";

const live = vi.hoisted(() => ({ push: null }));

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

// Stand in for the live socket: tests push branch updates by calling live.push(...)
vi.mock("../context/LiveUpdatesContext", () => ({
  BRANCH_EVENT: "branch:update",
  useLiveUpdates: (event, handler) => {
    live.push = handler;
    return { connected: true };
  },
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { name: "Anil Varghese", role: "staff" } }),
}));

beforeEach(() => vi.clearAllMocks());

function visit(overrides) {
  return {
    id: "v1",
    branch_name: "Kochi",
    slot_start: "2026-11-06T04:00:00Z",
    status: "booked",
    customer_name: "Lakshmi Nair",
    customer_phone_masked: "******0201",
    is_lead: false,
    is_walk_in: false,
    arrived_at: null,
    ...overrides,
  };
}

const TICKET = {
  id: "t1",
  reference: "GL-DEMO01",
  kind: "callback",
  message: "Please call me about the overdue interest.",
  preferred_time: "after 4 pm",
  status: "open",
  customer_name: "Arjun Menon",
  customer_phone_masked: "******0202",
};

function mockLoad(visits, tickets = []) {
  api.get.mockImplementation(async (url) => ({
    data: url === "/api/visits/branch" ? visits : tickets,
  }));
}

test("waiting, booked and callbacks are shown apart, phones masked", async () => {
  mockLoad(
    [
      visit({ id: "v1", status: "arrived", arrived_at: "2026-11-06T04:05:00Z" }),
      visit({ id: "v2", customer_name: "Fatima Sheikh", is_lead: true }),
    ],
    [TICKET],
  );
  render(<BranchQueue />);

  const waiting = (await screen.findByRole("heading", { name: /Waiting for valuation/ }))
    .parentElement.parentElement;
  expect(within(waiting).getByText(/Lakshmi Nair/)).toBeInTheDocument();
  expect(within(waiting).getByRole("button", { name: "Valuation done" })).toBeInTheDocument();
  expect(screen.getByText(/came from a loan estimate/)).toBeInTheDocument();
  expect(screen.getByText(/GL-DEMO01 · \*+0202 · call after 4 pm/)).toBeInTheDocument();
});

test("the customer-arrived button tells the server", async () => {
  const user = userEvent.setup();
  mockLoad([visit({})]);
  api.put.mockResolvedValue({ data: {} });
  render(<BranchQueue />);

  await user.click(await screen.findByRole("button", { name: "Customer arrived" }));

  expect(api.put).toHaveBeenCalledWith("/api/visits/v1/status", { status: "arrived" });
});

test("a booking made anywhere appears live", async () => {
  mockLoad([]);
  render(<BranchQueue />);
  await screen.findByText("No more bookings today.");

  act(() =>
    live.push({ branch_id: "b1", visits: [visit({ customer_name: "Ravi" })], tickets: [] }),
  );

  expect(screen.getByText(/Ravi/)).toBeInTheDocument();
});

test("a walk-in is added by name", async () => {
  const user = userEvent.setup();
  mockLoad([]);
  api.post.mockResolvedValue({ data: {} });
  render(<BranchQueue />);

  await user.type(await screen.findByLabelText("Walk-in customer's name"), "Suresh");
  await user.click(screen.getByRole("button", { name: "Add walk-in" }));

  expect(api.post).toHaveBeenCalledWith("/api/visits/walk-in", { name: "Suresh" });
});

test("a callback can be marked resolved", async () => {
  const user = userEvent.setup();
  mockLoad([], [TICKET]);
  api.put.mockResolvedValue({ data: {} });
  render(<BranchQueue />);

  await user.click(await screen.findByRole("button", { name: "Resolved" }));

  expect(api.put).toHaveBeenCalledWith("/api/tickets/t1/status", { status: "resolved" });
});
