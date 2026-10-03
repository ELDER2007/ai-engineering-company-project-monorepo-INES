"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ErrorNotice, LoadingNote } from "@/components/feedback";
import { clearToken, getToken } from "@/lib/token";
import { loginUrl } from "@/lib/returnTo";
import { useAuth } from "./AuthContext";

/** After this long checking the session, the person is offered a way out instead of an endless «Comprobando…». */
const SLOW_AFTER_MS = 6000;

/**
 * Layout guard (used by app/(app)/layout.tsx): renders its children only for a logged-in user; everyone else
 * goes to /login?next=<this page>, which sends them back here afterwards. Client-side only: the token lives
 * in localStorage, which the server (and Next.js middleware) can't read. It is a UX gate, not the security
 * boundary: the API answers 401 to any call without a valid token.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status, loggedOut, sessionError, retrySession, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  // Re-read on every navigation: the token may have been removed without going through clearToken()
  // (devtools, an extension). Read after mounting only: there is no localStorage on the server.
  const [hasToken, setHasToken] = useState<boolean | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    setHasToken(getToken() !== null);
  }, [pathname, status]);

  useEffect(() => {
    if (status === "authenticated" && hasToken === false) clearToken(); // the session state follows
  }, [status, hasToken]);

  useEffect(() => {
    if (status !== "anonymous") return;
    // After an explicit logout, whoever logs in next starts from the home page, not from this user's last view.
    const here = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    router.replace(loggedOut ? "/login" : loginUrl(here));
  }, [status, loggedOut, router]);

  useEffect(() => {
    setSlow(false);
    if (status !== "loading") return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [status]);

  if (status === "loading") {
    return (
      <div className="mx-auto max-w-md space-y-4 p-10">
        <LoadingNote label="Comprobando la sesión…" />
        {slow && (
          <ErrorNotice message="Está tardando más de lo normal." onRetry={retrySession} retryLabel="Volver a comprobar">
            <button type="button" onClick={logout} className="underline underline-offset-2 hover:text-white">
              Cerrar sesión
            </button>
          </ErrorNotice>
        )}
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="mx-auto max-w-md space-y-4 p-10">
        <ErrorNotice message={sessionError ?? "No se pudo comprobar la sesión."} onRetry={retrySession}>
          Tu sesión sigue guardada: cuando el servidor responda podrás continuar.{" "}
          <button type="button" onClick={logout} className="underline underline-offset-2 hover:text-white">
            Cerrar sesión
          </button>
        </ErrorNotice>
      </div>
    );
  }
  // Anonymous: the guard is already sending the person to the login page. Never show a protected view, even for one
  // frame, but do not leave a blank page if that redirect is slow.
  if (status === "anonymous") {
    return (
      <p className="p-10 text-sm text-slate-400">
        Redirigiendo a <Link href="/login" className="underline underline-offset-2 hover:text-white">iniciar sesión</Link>…
      </p>
    );
  }
  if (!hasToken) return null;
  return <>{children}</>;
}
