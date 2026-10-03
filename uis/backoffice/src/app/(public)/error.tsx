"use client";

import ErrorScreen from "@/components/ErrorScreen";

// The same for the screens that need no session (login, register): they used to have no fallback at all.
export default function PublicError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6">
      <ErrorScreen error={error} onRetry={retry} />
    </main>
  );
}
