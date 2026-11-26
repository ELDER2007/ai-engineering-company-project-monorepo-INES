"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { ApiError, resetPassword } from "../lib/api";
import { validateNewPassword } from "../lib/password";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-cyan-400 focus:outline-none aria-[invalid=true]:border-rose-500";

type Field = "password" | "confirmPassword";
type FieldErrors = Partial<Record<Field, string>>;

const INVALID_LINK = "El enlace no es válido o ha caducado. Solicita uno nuevo.";

/**
 * Where the emailed link lands (/reset-password?token=…). Public, and it works with or without a session:
 * the token alone says whose password is being reset. It never logs anybody in: on success it goes to
 * /login?reset=ok. Any failure says so and links to /forgot-password for a new link.
 */
export default function ResetPasswordPage() {
  // undefined = not read yet: the URL only exists in the browser, so the token is read after mounting.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [form, setForm] = useState<Record<Field, string>>({ password: "", confirmPassword: "" });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") || null);
  }, []);

  if (token === undefined) return null;

  if (token === null || linkInvalid) {
    return (
      <AuthShell title="Nueva contraseña">
        <div role="alert" className="mt-6 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {INVALID_LINK}
        </div>
        <Link
          href="/forgot-password"
          className="mt-6 flex w-full items-center justify-center rounded-full bg-cyan-400 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
        >
          Solicitar otro enlace
        </Link>
        <p className="mt-4 text-center text-sm text-slate-400">
          <Link href="/login" className="text-cyan-300 hover:text-cyan-200">
            Volver a iniciar sesión
          </Link>
        </p>
      </AuthShell>
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setError(null);
    const errors: FieldErrors = {};
    const passwordError = validateNewPassword(form.password, "La nueva contraseña");
    if (passwordError) errors.password = passwordError;
    if (form.confirmPassword !== form.password) errors.confirmPassword = "Las contraseñas no coinciden.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSubmitting(true);
    try {
      await resetPassword(token, form.password);
      router.replace("/login?reset=ok"); // the login page announces the success
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) setLinkInvalid(true);
      else if (err instanceof ApiError && err.status === 422 && err.fieldErrors.new_password)
        setFieldErrors({ password: err.fieldErrors.new_password });
      // A 422 about the token itself (empty, absurdly long) is a broken link, not a form mistake.
      else if (err instanceof ApiError && err.status === 422) setLinkInvalid(true);
      else setError("No se pudo cambiar la contraseña. Comprueba tu conexión e inténtalo de nuevo.");
      setSubmitting(false);
    }
  }

  const fieldProps = (field: Field) => ({
    type: "password",
    autoComplete: "new-password",
    value: form[field],
    onChange: (e: { target: { value: string } }) => {
      setForm((current) => ({ ...current, [field]: e.target.value }));
      setFieldErrors((current) => ({ ...current, [field]: undefined }));
    },
    "aria-invalid": fieldErrors[field] ? true : undefined,
    "aria-describedby": fieldErrors[field] ? `${field}-error` : undefined,
    className: `${inputClass} mt-1`,
  });
  const fieldError = (field: Field) =>
    fieldErrors[field] && (
      <span id={`${field}-error`} className="mt-1 block text-xs text-rose-300">
        {fieldErrors[field]}
      </span>
    );

  return (
    <AuthShell title="Nueva contraseña">
      <p className="mt-2 text-sm text-slate-400">Elige la contraseña con la que entrarás a partir de ahora.</p>
      <form onSubmit={handleSubmit} noValidate>
        <div className="mt-4 text-sm text-slate-300">
          <label className="block">
            Nueva contraseña
            <input {...fieldProps("password")} />
          </label>
          {fieldError("password")}
        </div>
        <div className="mt-4 text-sm text-slate-300">
          <label className="block">
            Repite la nueva contraseña
            <input {...fieldProps("confirmPassword")} />
          </label>
          {fieldError("confirmPassword")}
        </div>

        {error && (
          <div role="alert" className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {error}{" "}
            <Link href="/forgot-password" className="font-medium underline hover:text-rose-200">
              Solicitar un enlace nuevo
            </Link>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-60"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          Guardar contraseña
        </button>
      </form>
    </AuthShell>
  );
}
