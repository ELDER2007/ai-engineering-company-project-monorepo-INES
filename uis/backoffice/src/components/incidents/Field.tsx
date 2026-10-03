import type { ReactNode } from "react";
import { ErrorNotice } from "../feedback";

export const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-cyan-400 focus:outline-none aria-[invalid=true]:border-rose-400";

/** Label + control + inline error, wired for screen readers (the control must use `id`, `aria-invalid` and `aria-describedby`). */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="text-sm text-slate-300">
      <label htmlFor={id} className="block">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}

/** An error with, when it can help, a button to try again (see `ErrorNotice`). */
export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <ErrorNotice message={message} onRetry={onRetry} />;
}
