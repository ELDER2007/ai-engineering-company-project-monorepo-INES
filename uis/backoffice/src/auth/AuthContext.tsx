"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchMe, login as apiLogin, register as apiRegister, updateMyProfile } from "../lib/api";
import { describeError, isUnauthorized } from "../lib/errors";
import { clearToken, getToken, onTokenChange, onTokenChangeInOtherTab } from "../lib/token";
import type { Me, ProfileUpdate, SignUpPayload } from "../types/auth";

/**
 * After a successful sign-up: "authenticated" = logged in; "created" = the account exists but the automatic
 * login failed (network, or an admin switched the account off in between).
 */
export type RegisterResult = "authenticated" | "created";

/** "error": there is a token but the API could not say whether it is good (down, slow, answering badly). The
 *  session is kept and the person can try again: only a 401 means the session is over. */
type Status = "loading" | "anonymous" | "authenticated" | "error";

interface AuthState {
  status: Status;
  user: Me | null;
  /** What went wrong while checking the session (only when `status` is "error"). */
  sessionError: string | null;
  /** True after "Cerrar sesión" (not after a 401): the guard then sends to /login without a page to return to. */
  loggedOut: boolean;
  /** Set when the browser would not forget the session on "Cerrar sesión": the person must be told. */
  logoutWarning: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: SignUpPayload) => Promise<RegisterResult>;
  /** Asks again whether the stored session is good (after an "error"). */
  retrySession: () => void;
  /** Re-reads the session's user and profile from GET /auth/me. */
  refreshUser: () => Promise<void>;
  /** PUT /profiles/me, then the session's user carries the saved profile. */
  saveProfile: (update: ProfileUpdate) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Always "loading" at first, on the server too: localStorage only exists in the browser, so the token is
  // read after mounting (otherwise the server HTML and the first browser render would not match).
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<Me | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [loggedOut, setLoggedOut] = useState(false);
  const [logoutWarning, setLogoutWarning] = useState<string | null>(null);

  // Restore the session from the stored token (after a reload, or a login in another tab): the token is
  // only trusted once /auth/me accepts it.
  const restoreSession = useCallback(async (isCancelled: () => boolean = () => false) => {
    setStatus("loading");
    setSessionError(null);
    let next: Status = "error"; // whatever happens below, "loading" never outlives this function
    try {
      const me = await fetchMe();
      if (isCancelled()) return;
      setUser(me);
      next = "authenticated";
    } catch (err) {
      if (isCancelled()) return;
      if (isUnauthorized(err)) {
        // The token is no good (expired, or the account was removed or switched off): the session is over.
        clearToken();
        setUser(null);
        next = "anonymous";
      } else {
        // The API could not answer: keep the token, say so, and let the person try again.
        console.warn("[auth] the session could not be checked", err);
        setSessionError(describeError(err, "No se pudo comprobar la sesión."));
      }
    } finally {
      if (!isCancelled()) setStatus(next);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setStatus("anonymous");
      return;
    }
    let cancelled = false;
    void restoreSession(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [restoreSession]);

  // Another tab logged out (or cleared storage): drop the session here too. Another tab logged in (maybe as
  // someone else): load that session.
  useEffect(
    () =>
      onTokenChangeInOtherTab((token) => {
        if (token) void restoreSession();
        else {
          setUser(null);
          setStatus("anonymous");
        }
      }),
    [restoreSession],
  );

  // The API client clears the token on a 401 (expired, account removed): drop the session too.
  useEffect(
    () =>
      onTokenChange(() => {
        if (!getToken()) {
          setUser(null);
          setStatus("anonymous");
        }
      }),
    [],
  );

  const retrySession = useCallback(() => {
    if (getToken()) void restoreSession();
    else setStatus("anonymous");
  }, [restoreSession]);

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    let me: Me;
    try {
      me = await fetchMe();
    } catch (err) {
      clearToken(); // the login did not end in a usable session: do not leave the token behind
      throw err;
    }
    setUser(me);
    setStatus("authenticated");
    setLoggedOut(false);
    setLogoutWarning(null);
  }, []);

  // Sign up, then log straight in with the same credentials (the API creates sign-ups active).
  const register = useCallback(
    async (payload: SignUpPayload): Promise<RegisterResult> => {
      await apiRegister(payload);
      try {
        await login(payload.email, payload.password);
        return "authenticated";
      } catch (err) {
        // The account exists: never report this as a failed sign-up. The person is told to sign in.
        console.warn("[auth] the account was created but the automatic login failed", err);
        return "created";
      }
    },
    [login],
  );

  const refreshUser = useCallback(async () => {
    setUser(await fetchMe());
  }, []);

  const saveProfile = useCallback(async (update: ProfileUpdate) => {
    const profile = await updateMyProfile(update);
    setUser((current) => (current ? { ...current, profile } : current));
  }, []);

  const logout = useCallback(() => {
    setLoggedOut(true);
    const forgotten = clearToken();
    // Close the session on screen whatever the browser did; if it kept the token, say so.
    setUser(null);
    setStatus("anonymous");
    setLogoutWarning(
      forgotten
        ? null
        : "No se pudo borrar la sesión de este navegador. Cierra todas las ventanas del navegador o borra los datos del sitio.",
    );
  }, []);

  const value = useMemo(
    () => ({ status, user, sessionError, loggedOut, logoutWarning, login, register, retrySession, refreshUser, saveProfile, logout }),
    [status, user, sessionError, loggedOut, logoutWarning, login, register, retrySession, refreshUser, saveProfile, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
