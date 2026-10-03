import { ApiError } from "./api";

/** What a person can read when something fails: plain Spanish, never a status code, a field name or a server text.
 *  `fallback` is for errors that are not API errors (a bug in the screen, for instance). */
export function describeError(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  switch (err.kind) {
    case "timeout":
      return "El servidor tarda demasiado en responder. Inténtalo de nuevo en unos minutos.";
    case "network":
      return "No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.";
    case "storage":
      return "Tu navegador no permite guardar la sesión (¿modo privado o almacenamiento bloqueado?). Activa el almacenamiento del sitio e inténtalo de nuevo.";
    case "invalid-response":
      return "El servidor ha devuelto una respuesta que no se puede leer. Inténtalo de nuevo en unos minutos.";
  }
  const reference = err.errorId ? ` Si el problema continúa, indica esta referencia: ${err.errorId}.` : "";
  if (err.status === 401) return "Tu sesión ha caducado. Inicia sesión de nuevo.";
  if (err.status >= 500) return `El servidor ha tenido un problema. Inténtalo de nuevo en unos minutos.${reference}`;
  if (err.status === 403) return "No tienes permiso para hacer esto.";
  if (err.status === 404) return "No se encontró lo que buscabas. Puede que ya no exista.";
  if (err.status === 409) return "Esta acción ya no es posible porque los datos han cambiado. Hemos cargado los datos actuales.";
  if (err.status === 413) return "El archivo es demasiado grande.";
  if (err.status === 429) return "Demasiados intentos seguidos. Espera un momento e inténtalo de nuevo.";
  return fallback;
}

/** A failure worth offering «Reintentar» for: it may well work a moment later. */
export const isRetryable = (err: unknown) =>
  err instanceof ApiError && (err.kind === "network" || err.kind === "timeout" || err.kind === "invalid-response" || err.status >= 500);

export const isUnauthorized = (err: unknown) => err instanceof ApiError && err.status === 401;
export const isConflict = (err: unknown) => err instanceof ApiError && err.status === 409;
export const isNotFound = (err: unknown) => err instanceof ApiError && err.status === 404;

/** The same, for a file that cannot be analysed: says what to fix, not what the server said. */
export function describeUploadError(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.kind === "http") {
    if (err.status === 413) return "El archivo es demasiado grande (máximo 5 MB). Sube la exportación del helpdesk sin otros datos.";
    if (err.status === 422) {
      if (/Missing required columns/i.test(err.message))
        return "Este CSV no tiene las columnas esperadas. Sube la exportación del helpdesk, con las columnas ticket_id, date, client_company, category, description, agent_id, status, customer_email y satisfaction_score.";
      if (/no data rows/i.test(err.message)) return "El CSV solo tiene la cabecera, sin ninguna fila de datos. Sube un archivo con incidencias.";
      if (/\.csv file/i.test(err.message)) return "Solo se pueden analizar archivos .csv. Elige un archivo con esa extensión.";
      if (/UTF-8/i.test(err.message)) return "El archivo no está en formato UTF-8. Guárdalo como «CSV UTF-8» desde tu hoja de cálculo e inténtalo de nuevo.";
      if (/read as CSV/i.test(err.message)) return "No se pudo leer el archivo como CSV. Comprueba que es una exportación del helpdesk y no está dañado.";
      return "El archivo no se puede procesar. Comprueba que es la exportación CSV del helpdesk.";
    }
    if (err.status === 404) return "No hay ningún análisis que descargar todavía. Analiza primero un archivo CSV.";
  }
  return describeError(err, fallback);
}

const FIELD_TEXT: Record<string, string> = {
  title: "El título no es válido.",
  description: "La descripción no es válida.",
  category: "Selecciona una categoría.",
  origin: "Indica el origen de la incidencia.",
  branch: "Elige una de las oficinas de la lista.",
  customer_email: "Indica un email válido (ejemplo: cliente@empresa.com).",
  email: "Indica un email válido (ejemplo: nombre@empresa.com).",
  password: "La contraseña no es válida: debe tener entre 8 y 72 caracteres.",
  name: "El nombre no es válido.",
  phone: "El teléfono no es válido.",
  address: "La dirección no es válida.",
  monthly_rate: "La tarifa debe ser un número mayor que 0.",
};

/** The message shown next to a field the server rejected, in Spanish. `known` is what the form's own validation
 *  already says about that field, which is more specific when there is one. */
export function friendlyFieldError(field: string, type?: string, known?: string): string {
  if (known) return known;
  if (FIELD_TEXT[field]) return FIELD_TEXT[field];
  if (type === "missing") return "Este campo es obligatorio.";
  return "El valor no es válido. Revísalo e inténtalo de nuevo.";
}

/** `fieldErrors` of an ApiError, each one in Spanish. */
export function friendlyFieldErrors(err: ApiError): Record<string, string> {
  return Object.fromEntries(Object.keys(err.fieldErrors).map((field) => [field, friendlyFieldError(field)]));
}
