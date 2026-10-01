import type { Metadata } from "next";
import ResetPasswordPage from "@/views/ResetPasswordPage";

// The URL carries the reset token (?token=…): never send it to another site in a Referer header.
export const metadata: Metadata = { title: "Nueva contraseña", referrer: "no-referrer" };

export default ResetPasswordPage;
