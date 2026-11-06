import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import api from "../api";
import Assistant, { ACCOUNT_CHANGED } from "../components/Assistant";

const auth = vi.hoisted(() => ({ role: "customer" }));

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { post: vi.fn() },
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { name: "Lakshmi", role: auth.role } }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = "customer";
});

const HINDI_REPLY = {
  reply: "30 ग्राम 22 कैरेट सोने पर आपको लगभग ₹2,22,700 से ₹2,47,500 तक का लोन मिल सकता है।",
  session_id: "session-123",
  intent: "calculator",
  language: "hi",
  reply_language: "hi",
  disclaimer: "यह केवल एक अनुमान है।",
  blocked: false,
  tools_called: ["estimate_loan"],
};

async function openPanel(user) {
  render(<Assistant />);
  await user.click(screen.getByRole("button", { name: "Ask the assistant" }));
}

test("only customers get the assistant", () => {
  auth.role = "staff";

  render(<Assistant />);

  expect(screen.queryByRole("button", { name: "Ask the assistant" })).not.toBeInTheDocument();
});

test("the headline question as a suggestion gets a Hindi reply with its disclaimer", async () => {
  const user = userEvent.setup();
  api.post.mockResolvedValue({ data: HINDI_REPLY });
  await openPanel(user);

  await user.click(
    screen.getByRole("button", { name: "Mere paas 30 gram sona hai, kitna loan milega?" }),
  );

  expect(await screen.findByText(HINDI_REPLY.reply)).toHaveAttribute("lang", "hi");
  expect(screen.getByRole("note")).toHaveTextContent("यह केवल एक अनुमान है।");
  expect(api.post).toHaveBeenCalledWith("/api/chat", {
    message: "Mere paas 30 gram sona hai, kitna loan milega?",
  });
});

test("the conversation continues in the same session", async () => {
  const user = userEvent.setup();
  api.post.mockResolvedValue({ data: { ...HINDI_REPLY, disclaimer: null } });
  await openPanel(user);

  await user.type(screen.getByLabelText("Message to the assistant"), "hello");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findAllByText(HINDI_REPLY.reply);
  await user.type(screen.getByLabelText("Message to the assistant"), "and 24 carat?");
  await user.click(screen.getByRole("button", { name: "Send" }));

  expect(api.post).toHaveBeenLastCalledWith("/api/chat", {
    message: "and 24 carat?",
    session_id: "session-123",
  });
});

test("a failed message goes back into the box", async () => {
  const user = userEvent.setup();
  api.post.mockRejectedValue({ response: { status: 500, data: {} } });
  await openPanel(user);

  await user.type(screen.getByLabelText("Message to the assistant"), "my loan");
  await user.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("could not answer");
  expect(screen.getByLabelText("Message to the assistant")).toHaveValue("my loan");
});

test("a booking made by the assistant refreshes the pages that show it", async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  window.addEventListener(ACCOUNT_CHANGED, changed);
  api.post.mockResolvedValue({
    data: { ...HINDI_REPLY, reply: "Booked.", disclaimer: null, tools_called: ["book_visit"] },
  });
  await openPanel(user);

  await user.type(screen.getByLabelText("Message to the assistant"), "yes");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Booked.");

  expect(changed).toHaveBeenCalledTimes(1);
  window.removeEventListener(ACCOUNT_CHANGED, changed);
});
