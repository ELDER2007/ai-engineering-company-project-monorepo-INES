"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

// Unknown URLs go to the home page, which is protected: without a session the guard then sends to /login.
export default function NotFound() {
  const router = useRouter();
  useEffect(() => router.replace("/"), [router]);
  return (
    <p className="p-10 text-sm text-slate-400">
      Esa página no existe. Te llevamos al <Link href="/" className="underline underline-offset-2 hover:text-white">inicio</Link>…
    </p>
  );
}
