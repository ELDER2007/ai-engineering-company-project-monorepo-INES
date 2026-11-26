"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, MailCheck } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import AuthShell from "../components/AuthShell";
import { ApiError, requestPasswordReset } from "../lib/api";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-cyan-400 focus:outline-none aria-[invalid=true]:border-rose-500";

const SENT_MESSAGE = "Si esa dirección está registrada, recibirás un enlace en breve.";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  const { status } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  // With a session there is nothing to recover: the password is changed from /account/change-password.
  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [status, router]);

  if (status === "authenticated") return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (sent) return;
    setError(null);
    const address = email.trim();
    if (!address) return setEmailError("El email es obligatorio.");
    if (!EMAIL_PATTERN.test(address)) return setEmailError("El email no es válido.");

    setSubmitting(true);
    try {
      await requestPasswordReset(address);
      setSent(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setEmailError("El email no es válido.");
      else setError("No se pudo enviar la solicitud. Comprueba tu conexión e inténtalo de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="Recuperar contraseña">
      <p className="mt-2 text-sm text-slate-400">
        Escribe el email de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
      </p>
      <form onSubmit={handleSubmit} noValidate>
        <div className="mt-4 text-sm text-slate-300">
          <label className="block">
            Email
            <input
              type="email"
              autoComplete="username"
              disabled={sent || submitting}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setEmailError(null);
              }}
              aria-invalid={emailError ? true : undefined}
              aria-describedby={emailError ? "email-error" : undefined}
              className={`${inputClass} mt-1 disabled:opacity-60`}
            />
          </label>
          {emailError && (
            <span id="email-error" className="mt-1 block text-xs text-rose-300">
              {emailError}
            </span>
          )}
        </div>

        {sent && (
          // The same text whether the account exists or not: the API never says which.
          <div role="status" className="mt-4 flex gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            <MailCheck size={18} className="mt-0.5 shrink-0" />
            <p>{SENT_MESSAGE}</p>
          </div>
        )}

        {error && (
          <div role="alert" className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || sent}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-60"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          {sent ? "Enlace enviado" : "Enviar enlace"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-400">
        <Link href="/login" className="text-cyan-300 hover:text-cyan-200">
          Volver a iniciar sesión
        </Link>
      </p>
    </AuthShell>
  );
}
