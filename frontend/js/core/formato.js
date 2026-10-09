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

/* Sanitización para el HTML embebido que trae Core en algunos campos de
   texto (ej. dbo.sp_S2_Seguimiento: Estatus/Observaciones pueden incluir
   "<h3><i class='far fa-address-card'></i><br>Informacion Sobre Empresa
   Tenedora</h3>" para mostrar íconos y encabezados -- ver captura de Core).
   NO se puede mostrar con escapeHtml (saldría como texto literal) ni con
   innerHTML directo (esos mismos campos también pueden traer un comentario
   que el propio portal insertó en Core -- "Actualizar Core" --, y si
   alguien escribe algo como "<script>" ahí, renderizarlo tal cual sería
   una vulnerabilidad XSS). Esta función es una lista blanca: solo deja
   pasar las etiquetas de puro formato visual que usa Core (encabezados,
   íconos, negritas, saltos de línea) y solo los atributos class/style --
   cualquier otra etiqueta (script, img, a, iframe, svg, form...) o
   atributo (onclick, onerror, href, src...) se elimina por completo. */
const ETIQUETAS_HTML_PERMITIDAS = new Set([
  "H1", "H2", "H3", "H4", "H5", "H6", "I", "B", "STRONG", "EM", "BR",
  "SPAN", "P", "DIV", "SMALL", "U", "UL", "OL", "LI",
]);
const ATRIBUTOS_HTML_PERMITIDOS = new Set(["class", "style"]);
// Dentro de "style", nada que pueda ejecutar código o cargar un recurso
// externo (defensa adicional, aunque ya no debería quedar ninguna
// etiqueta/atributo capaz de eso tras la lista blanca de arriba).
const PATRON_ESTILO_PELIGROSO = /url\s*\(|expression\s*\(|javascript:/i;

function limpiarHijosHtml(nodo) {
  [...nodo.childNodes].forEach((hijo) => {
    if (hijo.nodeType === Node.TEXT_NODE) return;
    if (hijo.nodeType !== Node.ELEMENT_NODE || !ETIQUETAS_HTML_PERMITIDAS.has(hijo.tagName)) {
      hijo.remove(); // quita la etiqueta Y su contenido -- nunca se deja caer a texto
      return;
    }
    [...hijo.attributes].forEach((attr) => {
      if (!ATRIBUTOS_HTML_PERMITIDOS.has(attr.name.toLowerCase())) hijo.removeAttribute(attr.name);
    });
    const estilo = hijo.getAttribute("style");
    if (estilo && PATRON_ESTILO_PELIGROSO.test(estilo)) hijo.removeAttribute("style");
    limpiarHijosHtml(hijo);
  });
}

export function sanitizarHtmlSeguimiento(html) {
  if (html === null || html === undefined) return "";
  // <template>: su contenido es inerte (no ejecuta scripts, no carga
  // imágenes/recursos) hasta que se inserta en el documento vivo -- para
  // entonces ya se habrá limpiado todo lo peligroso.
  const plantilla = document.createElement("template");
  plantilla.innerHTML = String(html);
  limpiarHijosHtml(plantilla.content);
  return plantilla.innerHTML;
}
