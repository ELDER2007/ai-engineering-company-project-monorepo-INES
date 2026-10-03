"use client";

import { useEffect } from "react";

/**
 * The screen of last resort, shared by app/(app)/error.tsx, app/(public)/error.tsx and app/global-error.tsx:
 * what happened in plain words, a button to try again, a way home and, if it keeps happening, what to tell
 * the support team. The error is written to the browser console; its `digest` (the reference the server logged
 * for it) is shown so a report can be matched with its cause.
 */
export default function ErrorScreen({ error, onRetry }: { error: Error & { digest?: string }; onRetry: () => void }) {
  useEffect(() => {
    console.error("[ui] a screen failed to render", error);
  }, [error]);

  return (
    <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-200">
      <h1 className="text-xl font-semibold text-white">Algo ha salido mal</h1>
      <p className="mt-2 text-sm">Ha ocurrido un error inesperado al mostrar esta pantalla. Tus datos no se han perdido.</p>
      <p className="mt-2 text-sm">
        Si el problema continúa, avisa al equipo de soporte{error.digest ? ` e indica esta referencia: ${error.digest}` : ""}.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button type="button" onClick={onRetry} className="rounded-full bg-cyan-400 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300">
          Reintentar
        </button>
        {/* A plain link on purpose: it must work even when the router or the layout is what failed. */}
        <a href="/" className="text-sm text-slate-200 underline underline-offset-2 hover:text-white">
          Volver al inicio
        </a>
      </div>
    </div>
  );
}
