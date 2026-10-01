"use client";

import { useState, type FormEvent } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { ApiError, changePassword } from "../lib/api";
import { validateNewPassword } from "../lib/password";

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-cyan-400 focus:outline-none aria-[invalid=true]:border-rose-500";

type Field = "currentPassword" | "newPassword" | "confirmPassword";
type FieldErrors = Partial<Record<Field, string>>;
type Form = Record<Field, string>;

const emptyForm: Form = { currentPassword: "", newPassword: "", confirmPassword: "" };
const SAME_PASSWORD = "La nueva contraseña debe ser distinta de la actual.";

function validate(form: Form): FieldErrors {
  const errors: FieldErrors = {};
  if (!form.currentPassword) errors.currentPassword = "La contraseña actual es obligatoria.";
  const newPasswordError = validateNewPassword(form.newPassword, "La nueva contraseña");
  if (newPasswordError) errors.newPassword = newPasswordError;
  else if (form.newPassword === form.currentPassword) errors.newPassword = SAME_PASSWORD;
  if (form.confirmPassword !== form.newPassword) errors.confirmPassword = "Las contraseñas no coinciden.";
  return errors;
}

export default function ChangePasswordPage() {
  const [form, setForm] = useState<Form>(emptyForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const errors = validate(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSaving(true);
    try {
      await changePassword(form.currentPassword, form.newPassword);
      setForm(emptyForm);
      setSaved(true);
    } catch (err) {
      // A 401 never lands here visibly: the API client drops the token and RequireAuth sends to /login.
      // That is why a wrong current password is a 400: it must not end the session.
      if (err instanceof ApiError && err.status === 400)
        setFieldErrors({ currentPassword: "La contraseña actual no es correcta." });
      else if (err instanceof ApiError && err.status === 422)
        setFieldErrors({ newPassword: err.fieldErrors.new_password ?? SAME_PASSWORD });
      else setError("No se pudo cambiar la contraseña. Inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  const fieldProps = (field: Field) => ({
    id: field,
    type: "password",
    value: form[field],
    onChange: (e: { target: { value: string } }) => {
      setForm((current) => ({ ...current, [field]: e.target.value }));
      setFieldErrors((current) => ({ ...current, [field]: undefined }));
      setSaved(false);
    },
    "aria-invalid": fieldErrors[field] ? true : undefined,
    "aria-describedby": fieldErrors[field] ? `${field}-error` : undefined,
    className: inputClass,
  });
  const fieldError = (field: Field) =>
    fieldErrors[field] && (
      <span id={`${field}-error`} className="mt-1 block text-xs text-rose-300">
        {fieldErrors[field]}
      </span>
    );

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold text-white">Cambiar contraseña</h1>
      <p className="mt-2 text-slate-400">
        Necesitas tu contraseña actual. Te avisaremos por correo cuando se haya cambiado.
      </p>

      <form onSubmit={handleSubmit} noValidate className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="text-sm text-slate-300">
          <label htmlFor="currentPassword">Contraseña actual</label>
          <input autoComplete="current-password" {...fieldProps("currentPassword")} />
          {fieldError("currentPassword")}
        </div>
        <div className="mt-4 text-sm text-slate-300">
          <label htmlFor="newPassword">Nueva contraseña</label>
          <input autoComplete="new-password" {...fieldProps("newPassword")} />
          {fieldError("newPassword")}
        </div>
        <div className="mt-4 text-sm text-slate-300">
          <label htmlFor="confirmPassword">Repite la nueva contraseña</label>
          <input autoComplete="new-password" {...fieldProps("confirmPassword")} />
          {fieldError("confirmPassword")}
        </div>

        {error && (
          <div role="alert" className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {error}
          </div>
        )}
        {saved && (
          <div role="status" className="mt-4 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            <CheckCircle2 size={16} />
            Contraseña cambiada. Úsala la próxima vez que inicies sesión.
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="mt-6 flex items-center gap-2 rounded-full bg-cyan-400 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-60"
        >
          {saving && <Loader2 size={16} className="animate-spin" />}
          Cambiar contraseña
        </button>
      </form>
    </div>
  );
}
