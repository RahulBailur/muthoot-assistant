import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { io } from "socket.io-client";

import { useAuth } from "./AuthContext";

// What the server pushes. It decides who gets what: staff get their own branch, a customer
// only their own visits.
export const BRANCH_EVENT = "branch:update";
export const VISIT_EVENT = "visit:update";
const EVENTS = [BRANCH_EVENT, VISIT_EVENT];

const LiveUpdatesContext = createContext(null);

/** One authenticated Socket.IO connection per signed-in session, shared by every screen. */
export function LiveUpdatesProvider({ children }) {
  const { token } = useAuth();
  const listeners = useRef(new Set());
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!token) return;
    const socket = io({ auth: { token }, transports: ["websocket"] });
    socket.on("connect", () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));
    EVENTS.forEach((event) =>
      socket.on(event, (data) => listeners.current.forEach((listener) => listener(event, data))),
    );
    return () => {
      socket.disconnect();
      setConnected(false);
    };
  }, [token]);

  const value = useMemo(
    () => ({
      connected,
      subscribe(listener) {
        listeners.current.add(listener);
        return () => listeners.current.delete(listener);
      },
    }),
    [connected],
  );
  return <LiveUpdatesContext.Provider value={value}>{children}</LiveUpdatesContext.Provider>;
}

/** Call `handler` with every live update of one kind the server sends this user. */
export function useLiveUpdates(event, handler) {
  const context = useContext(LiveUpdatesContext);
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const subscribe = context?.subscribe;
  useEffect(
    () => subscribe?.((kind, data) => kind === event && latest.current(data)),
    [subscribe, event],
  );
  return { connected: context?.connected ?? false };
}
