"use client";

import ErrorScreen from "@/components/ErrorScreen";

// Last line of defence for the protected screens: an unexpected rendering error shows this instead of a blank page.
// `retry` asks Next.js to fetch and draw the segment again (see node_modules/next/dist/docs, error.js).
export default function AppError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorScreen error={error} onRetry={retry} />;
}
