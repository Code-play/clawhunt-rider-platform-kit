import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import * as api from '../api/client.js';

const SESSION_KEY = 'rider.admin.session';

function readSession() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    const saved = readSession();
    if (saved && saved.token) api.setAuthToken(saved.token);
    return saved;
  });

  const login = useCallback(async ({ username, password }) => {
    const res = await api.login({ username, password });
    const next = { token: res.token, user: res.user };
    api.setAuthToken(next.token);
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    setSession(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    api.setAuthToken('');
    window.sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({
      session,
      user: (session && session.user) || null,
      token: (session && session.token) || '',
      isAuthenticated: Boolean(session && session.token),
      login,
      logout,
    }),
    [session, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return ctx;
}
