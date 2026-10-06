/* Formato de texto y fechas para pintar en pantalla.
   Fechas siempre como aaaa-mm-dd (ej. 2026-05-05), y con hora como
   aaaa-mm-dd HH:mm (24 h), sin depender del idioma del navegador. */

export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const dosDigitos = (n) => String(n).padStart(2, "0");

function aaaammdd(d) {
  return `${d.getFullYear()}-${dosDigitos(d.getMonth() + 1)}-${dosDigitos(d.getDate())}`;
}

export function formatDate(iso) {
  if (!iso) return "—";
  // Si ya viene como "aaaa-mm-dd" (con o sin hora), se toma tal cual: así no
  // hay corrimientos de un día por zona horaria al convertirla a Date.
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  if (m) return m[1];
  const d = new Date(iso);
  return isNaN(d) ? iso : aaaammdd(d);
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return `${aaaammdd(d)} ${dosDigitos(d.getHours())}:${dosDigitos(d.getMinutes())}`;
}
