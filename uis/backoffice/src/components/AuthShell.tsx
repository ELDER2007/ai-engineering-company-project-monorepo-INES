import type { ReactNode } from "react";

/** The centered card of the public pages (sign-up, forgotten and reset password). */
export default function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <p className="text-xl font-black text-white">
          nexova<span className="text-cyan-400">.</span>
        </p>
        <p className="text-xs uppercase tracking-widest text-slate-500">Backoffice</p>
        <h1 className="mt-6 text-lg font-semibold text-white">{title}</h1>
        {children}
      </div>
    </div>
  );
}
