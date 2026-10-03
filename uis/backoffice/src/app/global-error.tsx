"use client";

// Replaces the root layout when the layout itself (or the session provider) fails: without this file Next.js shows its
// own English page. It must draw its own <html> and <body> and load the styles itself (see error.js in the Next docs).
import ErrorScreen from "@/components/ErrorScreen";
import "./globals.css";

export default function GlobalError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="es">
      <body className="bg-slate-950">
        <main className="flex min-h-screen items-center justify-center p-6">
          <ErrorScreen error={error} onRetry={retry} />
        </main>
      </body>
    </html>
  );
}
