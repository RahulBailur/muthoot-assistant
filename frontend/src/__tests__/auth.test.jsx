import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import api from "../api";
import DemoBanner from "../components/DemoBanner";
import ProtectedRoute from "../components/ProtectedRoute";
import { AuthProvider } from "../context/AuthContext";
import Login from "../pages/Login";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { response: { use: vi.fn(), eject: vi.fn() } },
  },
}));

const CUSTOMER = { id: "c1", name: "Lakshmi", phone_masked: "******0201", role: "customer" };

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <p>Home page</p>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

test("the demo banner warns never to enter a real OTP or account number", () => {
  render(<DemoBanner />);

  expect(screen.getByRole("note")).toHaveTextContent("Never enter a real account number, OTP");
});

test("a signed-out visitor is sent to the login page", () => {
  renderAt("/");

  expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
});

describe("customer login", () => {
  test("phone, then the code, then home", async () => {
    const user = userEvent.setup();
    api.post
      .mockResolvedValueOnce({
        data: { sent_to: "******0201", expires_in_s: 300, demo_otp: "482913" },
      })
      .mockResolvedValueOnce({ data: { access_token: "jwt", user: CUSTOMER } });
    renderAt("/login");

    await user.type(screen.getByLabelText("Mobile number"), "9000000201");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByText(/sent a 6-digit code to \*+0201/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("482913");
    await user.type(screen.getByLabelText("Code"), "482913");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(api.post).toHaveBeenNthCalledWith(1, "/api/auth/otp/request", { phone: "9000000201" });
    expect(api.post).toHaveBeenNthCalledWith(2, "/api/auth/otp/verify", {
      phone: "9000000201",
      otp: "482913",
    });
    expect(sessionStorage.getItem("goldloan_token")).toBe("jwt");
    expect(localStorage.getItem("goldloan_token")).toBeNull(); // other tabs are not logged in
  });

  test("the code screen says the assistant will never ask for it", async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValueOnce({ data: { sent_to: "******0201", demo_otp: null } });
    renderAt("/login");

    await user.type(screen.getByLabelText("Mobile number"), "9000000201");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByText(/the assistant will never ask for it/)).toBeInTheDocument();
  });

  test("an invalid mobile number is caught before anything is sent", async () => {
    const user = userEvent.setup();
    renderAt("/login");

    await user.type(screen.getByLabelText("Mobile number"), "12345");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(screen.getByRole("alert")).toHaveTextContent("10-digit Indian mobile number");
    expect(api.post).not.toHaveBeenCalled();
  });

  test("a wrong code is explained", async () => {
    const user = userEvent.setup();
    api.post
      .mockResolvedValueOnce({ data: { sent_to: "******0201", demo_otp: "482913" } })
      .mockRejectedValueOnce({ response: { status: 401, data: { detail: "Incorrect OTP" } } });
    renderAt("/login");

    await user.type(screen.getByLabelText("Mobile number"), "9000000201");
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(await screen.findByLabelText("Code"), "000000");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect OTP");
  });
});

test("branch staff log in with a password", async () => {
  const user = userEvent.setup();
  api.post.mockResolvedValueOnce({
    data: { access_token: "jwt", user: { ...CUSTOMER, role: "staff" } },
  });
  renderAt("/login");

  await user.click(screen.getByRole("tab", { name: "Branch staff or admin" }));
  await user.type(screen.getByLabelText("Mobile number"), "9000000101");
  await user.type(screen.getByLabelText("Password"), "secret-pass");
  await user.click(screen.getByRole("button", { name: "Log in" }));

  expect(await screen.findByText("Home page")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("/api/auth/login", {
    phone: "9000000101",
    password: "secret-pass",
  });
});
