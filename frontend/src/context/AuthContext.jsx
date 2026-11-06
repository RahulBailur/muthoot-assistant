import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import api, { tokenStore } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => tokenStore.get());
  // True until we know whether a stored token still works
  const [loading, setLoading] = useState(() => Boolean(tokenStore.get()));

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    setUser(null);
  }, []);

  const startSession = useCallback((data) => {
    tokenStore.set(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  /** Customers: step one sends a (mock) OTP. Returns what the server says about it. */
  const requestOtp = useCallback(
    async (phone) => (await api.post("/api/auth/otp/request", { phone })).data,
    [],
  );

  /** Customers: step two checks it. A first-time phone becomes a new customer. */
  const verifyOtp = useCallback(
    async (phone, otp, name) =>
      startSession(
        (await api.post("/api/auth/otp/verify", { phone, otp, ...(name && { name }) })).data,
      ),
    [startSession],
  );

  /** Branch staff and admin. */
  const login = useCallback(
    async (phone, password) =>
      startSession((await api.post("/api/auth/login", { phone, password })).data),
    [startSession],
  );

  // Restore the session after a reload
  useEffect(() => {
    if (!tokenStore.get()) return;
    let cancelled = false;
    api
      .get("/api/auth/me")
      .then((response) => !cancelled && setUser(response.data))
      .catch(() => !cancelled && logout())
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [logout]);

  // An expired or revoked token anywhere in the app ends the session
  useEffect(() => {
    const id = api.interceptors.response.use(undefined, (error) => {
      const url = error.config?.url ?? "";
      if (error.response?.status === 401 && !url.startsWith("/api/auth/")) logout();
      return Promise.reject(error);
    });
    return () => api.interceptors.response.eject(id);
  }, [logout]);

  const value = useMemo(
    () => ({ user, token, loading, requestOtp, verifyOtp, login, logout }),
    [user, token, loading, requestOtp, verifyOtp, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
