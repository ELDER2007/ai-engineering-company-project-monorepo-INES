"use client";

// The three states of anything that asks the API for something, drawn the same way everywhere:
// loading (LoadingNote), success (SuccessNotice) and error (ErrorNotice, with a way out).
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { catchError, type ErrorInfo } from "next/error";
import { Loader2 } from "lucide-react";

export function LoadingNote({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 text-sm text-slate-300">
      <Loader2 className="animate-spin text-cyan-300" size={18} aria-hidden="true" />
      {label}
    </div>
  );
}

export function SuccessNotice({ message }: { message: string }) {
  return (
    <p role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
      {message}
    </p>
  );
}

const buttonClass = "rounded-full border border-slate-600 px-4 py-1.5 text-sm font-medium text-slate-100 hover:border-cyan-400 hover:text-white";

/** An error and what to do about it: a button to try again, and/or a link home, and/or an instruction (`children`). */
export function ErrorNotice({
  message,
  onRetry,
  retryLabel = "Reintentar",
  home = false,
  children,
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  home?: boolean;
  children?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
      <p>{message}</p>
      {children && <div className="mt-2 text-rose-200/90">{children}</div>}
      {(onRetry || home) && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {onRetry && (
            <button type="button" onClick={onRetry} className={buttonClass}>
              {retryLabel}
            </button>
          )}
          {home && (
            <Link href="/" className="text-sm text-slate-200 underline underline-offset-2 hover:text-white">
              Volver al inicio
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function LogOnce({ name, error }: { name: string; error: unknown }) {
  useEffect(() => {
    console.error(`[ui] ${name} could not be shown`, error);
  }, [name, error]);
  return null;
}

function SectionFallback(props: { name: string }, { error, retry }: ErrorInfo) {
  return (
    <>
      <LogOnce name={props.name} error={error} />
      <ErrorNotice message={`No se pudo mostrar ${props.name}.`} onRetry={() => retry()} />
    </>
  );
}

/** Wrap a part of a screen in it: if that part fails to draw, only its box is replaced by an error with a retry
 *  and the rest of the page keeps working. `<SectionBoundary name="el resumen">…</SectionBoundary>` */
export const SectionBoundary = catchError(SectionFallback);
