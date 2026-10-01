// Limits of a new password, the same the API enforces (services/api/users/schemas.py, NewPassword). Shared by
// the sign-up, reset-password and change-password forms, so all three reject what the API would reject.
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX_BYTES = 72; // bcrypt only reads the first 72 bytes

/** Spanish message if the password breaks the rules; `label` names the field ("La contraseña"). */
export function validateNewPassword(password: string, label = "La contraseña"): string | undefined {
  if (!password) return `${label} es obligatoria.`;
  if (password.length < PASSWORD_MIN) return `${label} debe tener al menos ${PASSWORD_MIN} caracteres.`;
  if (new TextEncoder().encode(password).length > PASSWORD_MAX_BYTES)
    return `${label} es demasiado larga (máximo ${PASSWORD_MAX_BYTES} bytes).`;
  return undefined;
}
