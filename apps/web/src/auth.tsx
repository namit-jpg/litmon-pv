import React, { createContext, useContext, useMemo, useState } from "react";
import { api, setToken, User } from "./api";

type AuthCtx = {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(
    () => localStorage.getItem("litmon_token")
  );
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem("litmon_user");
    return raw ? JSON.parse(raw) : null;
  });

  const value = useMemo<AuthCtx>(
    () => ({
      user,
      token,
      async login(email, password) {
        const t = await api.login(email, password);
        setToken(t.access_token);
        setTok(t.access_token);
        localStorage.setItem("litmon_token", t.access_token);
        const me = await api.me();
        setUser(me);
        localStorage.setItem("litmon_user", JSON.stringify(me));
      },
      logout() {
        setToken(null);
        setTok(null);
        setUser(null);
        localStorage.removeItem("litmon_token");
        localStorage.removeItem("litmon_user");
      },
    }),
    [user, token]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
