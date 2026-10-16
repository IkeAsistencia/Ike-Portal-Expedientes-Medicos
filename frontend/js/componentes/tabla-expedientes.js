/* Tabla de expedientes (columnas fijas a la izquierda, casillas de
   selección y liga al Seguimiento). La usan Expedientes y Expedientes PA. */
import { escapeHtml, formatDate, formatDateTime } from "../core/formato.js";
import { esPerfilAdministrador } from "../core/sesion.js";

export const COLUMNAS_TABLA = 18;

/* Columnas de la tabla, en orden. La tabla usa anchos FIJOS (table-layout:
   fixed): así cada columna mide exactamente lo que dice aquí y el
   desplazamiento "left" de las columnas fijas (las primeras, que se quedan
   al hacer scroll horizontal) coincide con su posición real -- si no,
   quedaban huecos entre ellas y la primera columna que sigue (Titular)
   quedaba tapada por las fijas. Solo se fijan hasta Cuenta para dejar
   espacio a Titular y al resto. */
const COLUMNAS = [
  { w: 40, fija: true },    // #
  { w: 36, fija: true },    // casilla
  { w: 135, fija: true },   // Fecha Apertura
  { w: 95, fija: true },    // Expediente
  { w: 115, fija: true },   // ⏱ Tiempo
  { w: 240, fija: true },   // Cuenta
  { w: 135 },               // Servicio
  { w: 150 },               // Subservicio
  { w: 340 },               // Titular
  { w: 230 },               // Paciente
  { w: 150 },               // Especialidad
  { w: 130 },               // Entidad
  { w: 150 },               // Municipio
  { w: 200 },               // Fecha Asignación Proveedor
  { w: 105 },               // Fecha Cita
  { w: 120 },               // Teléfono
  { w: 230 },               // Correo
  { w: 175 },               // Estado
];
const ULTIMA_FIJA = COLUMNAS.reduce((u, c, i) => (c.fija ? i : u), 0);
const IZQUIERDA = [];
let anchoTotal = 0;
COLUMNAS.forEach((c) => { IZQUIERDA.push(anchoTotal); anchoTotal += c.w; });

/* Clases y estilo de una celda según su columna (las fijas llevan su "left"). */
function celda(i) {
  if (!COLUMNAS[i].fija) return "";
  return ` class="col-frozen${i === ULTIMA_FIJA ? " col-frozen-last" : ""}" style="left:${IZQUIERDA[i]}px;"`;
}

/* Celda de texto: se corta con "…" si no cabe y el valor completo sale al pasar el cursor. */
function celdaTexto(i, texto) {
  const t = texto == null ? "" : String(texto);
  return `<td${celda(i)} title="${escapeHtml(t)}">${escapeHtml(t)}</td>`;
}

export function badgeEstatus(estatus) {
  const map = {
    "Abierto": "pendiente",
    "En Espera de Respuesta": "espera",
    "Seguimiento Proveedor": "seguimiento",
    "Seguimiento de Cita": "programado",
    "Finalizado": "activo",
  };
  const cls = map[estatus] || "pendiente";
  return `<span class="badge ${cls}">${escapeHtml(estatus)}</span>`;
}

const SIGNIFICADO_SEMAFORO = {
  verde: "Semáforo: en tiempo",
  amarillo: "Semáforo: por vencer",
  naranja: "Semáforo: urgente",
  rojo: "Semáforo: vencido",
};

/* Punto de color del semáforo (distinto del badge de Estado, ver sección 1
   de "Puntos a modificar.docx"). null = no aplica (ya hay respuesta del
   proveedor o el caso ya avanzó) -- se muestra un punto gris neutro. */
export function puntoSemaforo(color, tiempo) {
  const titulo = SIGNIFICADO_SEMAFORO[color] || "Semáforo: no aplica (ya tiene respuesta o avanzó)";
  const clase = color ? escapeHtml(color) : "";
  const texto = tiempo ? `<span class="semaforo-tiempo">${escapeHtml(tiempo)}</span>` : "";
  return `<span class="semaforo-celda" title="${titulo}${tiempo ? " · " + escapeHtml(tiempo) : ""}"><span class="semaforo-punto ${clase}"></span>${texto}</span>`;
}

/* Color y prefijo de la cuenta (módulo "Colores de Cuentas"): el renglón se
   pinta del color de la cuenta y el prefijo sale junto a su nombre. */
function claseFila(r) {
  return r.cuenta_color ? ` class="fila-cta cta-${escapeHtml(String(r.cuenta_color).replace(/[^a-z]/g, ""))}"` : "";
}

function celdaCuenta(r) {
  const chip = r.cuenta_prefijo ? `<span class="cta-chip">${escapeHtml(r.cuenta_prefijo)}</span>` : "";
  if (!chip) return escapeHtml(r.cuenta);
  return `<span class="cta-celda" title="${escapeHtml(r.cuenta)}">${chip}<span class="cta-nombre">${escapeHtml(r.cuenta)}</span></span>`;
}

function celdaExpediente(numeroExpediente) {
  // Administrador solo busca/selecciona para el corte -- no entra al detalle
  // de Seguimiento (esa pantalla es trabajo operativo de Cabina/Proveedor).
  if (esPerfilAdministrador()) return escapeHtml(String(numeroExpediente));
  return `<a href="#" class="link-expediente" data-exp="${numeroExpediente}">${numeroExpediente}</a>`;
}

export function tablaExpedientesHtml({ idTabla, idChkTodos, idTbody, mensajeInicial }) {
  return `
    <table class="tabla-expedientes" id="${idTabla}" style="width:${anchoTotal}px;">
      <colgroup>${COLUMNAS.map(c => `<col style="width:${c.w}px;">`).join("")}</colgroup>
      <thead>
        <tr>
          <th${celda(0)}>#</th>
          <th${celda(1)}><input type="checkbox" id="${idChkTodos}"></th>
          <th${celda(2)}>Fecha Apertura</th>
          <th${celda(3)}>Expediente</th>
          <th${celda(4)} title="Semáforo del expediente y tiempo transcurrido">⏱ Tiempo</th>
          <th${celda(5)}>Cuenta</th>
          <th${celda(6)}>Servicio</th>
          <th${celda(7)}>Subservicio</th>
          <th${celda(8)}>Titular</th><th${celda(9)}>Paciente</th><th${celda(10)}>Especialidad</th>
          <th${celda(11)}>Entidad</th><th${celda(12)}>Municipio</th><th${celda(13)}>Fecha Asignación Proveedor</th>
          <th${celda(14)}>Fecha Cita</th><th${celda(15)}>Teléfono</th><th${celda(16)}>Correo</th><th${celda(17)}>Estado</th>
        </tr>
      </thead>
      <tbody id="${idTbody}">
        <tr><td colspan="${COLUMNAS_TABLA}" class="empty">${mensajeInicial}</td></tr>
      </tbody>
    </table>`;
}

/* Mensaje de una sola celda a lo ancho de la tabla (cargando, vacío, error). */
export function filaMensaje(tbody, mensaje, clase = "empty") {
  tbody.innerHTML = `<tr><td colspan="${COLUMNAS_TABLA}" class="${clase}">${mensaje}</td></tr>`;
}

/* Pinta las filas de una página.
   - inicio: índice (base 0) de la primera fila, para la columna "#".
   - seleccionados: Set de números de expediente marcados.
   - alAbrir(expediente): clic en el número de expediente.
   - alCambiarSeleccion(): se marcó/desmarcó alguna casilla. */
export function renderFilasExpedientes(tbody, filas, { inicio, seleccionados, alAbrir, alCambiarSeleccion }) {
  tbody.innerHTML = filas.map((r, i) => `
    <tr${claseFila(r)}>
      <td${celda(0)}>${inicio + i + 1}</td>
      <td${celda(1)}><input type="checkbox" class="chk-expediente" data-exp="${r.expediente}" ${seleccionados.has(r.expediente) ? "checked" : ""}></td>
      <td${celda(2)}>${formatDateTime(r.fecha_apertura_completa)}</td>
      <td${celda(3)}>${celdaExpediente(r.expediente)}</td>
      <td${celda(4)}>${puntoSemaforo(r.color_semaforo, r.tiempo_semaforo)}</td>
      <td${celda(5)}>${celdaCuenta(r)}</td>
      ${celdaTexto(6, r.tipo_servicio)}
      ${celdaTexto(7, r.tipo_subservicio)}
      ${celdaTexto(8, r.nombre_titular)}
      ${celdaTexto(9, r.nombre_paciente)}
      ${celdaTexto(10, r.especialidad)}
      ${celdaTexto(11, r.entidad)}
      ${celdaTexto(12, r.municipio)}
      <td${celda(13)}>${r.fecha_asignacion_proveedor ? formatDate(r.fecha_asignacion_proveedor) : '<span class="muted">Sin asignar</span>'}</td>
      <td${celda(14)}>${r.fecha_cita ? formatDate(r.fecha_cita) : '<span class="muted">Sin cita</span>'}</td>
      ${celdaTexto(15, r.telefono)}
      ${celdaTexto(16, r.email)}
      <td${celda(17)}>${badgeEstatus(r.estatus)}</td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".link-expediente").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      alAbrir(parseInt(a.dataset.exp, 10));
    });
  });

  tbody.querySelectorAll(".chk-expediente").forEach(chk => {
    chk.addEventListener("change", (e) => {
      const exp = parseInt(e.target.dataset.exp, 10);
      if (e.target.checked) seleccionados.add(exp);
      else seleccionados.delete(exp);
      alCambiarSeleccion();
    });
  });
}
