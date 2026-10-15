/* Tabla de expedientes (columnas fijas a la izquierda, casillas de
   selección y liga al Seguimiento). La usan Expedientes y Expedientes PA. */
import { escapeHtml, formatDate, formatDateTime } from "../core/formato.js";
import { esPerfilAdministrador } from "../core/sesion.js";

export const COLUMNAS_TABLA = 18;

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

function celdaExpediente(numeroExpediente) {
  // Administrador solo busca/selecciona para el corte -- no entra al detalle
  // de Seguimiento (esa pantalla es trabajo operativo de Cabina/Proveedor).
  if (esPerfilAdministrador()) return escapeHtml(String(numeroExpediente));
  return `<a href="#" class="link-expediente" data-exp="${numeroExpediente}">${numeroExpediente}</a>`;
}

export function tablaExpedientesHtml({ idTabla, idChkTodos, idTbody, mensajeInicial }) {
  return `
    <table class="tabla-expedientes" id="${idTabla}">
      <thead>
        <tr>
          <th class="col-frozen" style="width:40px;left:0;">#</th>
          <th class="col-frozen" style="width:32px;left:40px;"><input type="checkbox" id="${idChkTodos}"></th>
          <th class="col-frozen" style="width:140px;left:72px;">Fecha Apertura</th>
          <th class="col-frozen" style="width:100px;left:212px;">Expediente</th>
          <th class="col-frozen" style="width:120px;left:312px;" title="Semáforo del expediente y tiempo transcurrido">⏱ Tiempo</th>
          <th class="col-frozen" style="width:190px;left:432px;">Cuenta</th>
          <th class="col-frozen" style="width:130px;left:622px;">Servicio</th>
          <th class="col-frozen col-frozen-last" style="width:150px;left:752px;">Subservicio</th>
          <th>Titular</th><th>Paciente</th><th>Especialidad</th>
          <th>Entidad</th><th>Municipio</th><th>Fecha Asignación Proveedor</th>
          <th>Fecha Cita</th><th>Teléfono</th><th>Correo</th><th>Estado</th>
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
    <tr>
      <td class="col-frozen" style="left:0;">${inicio + i + 1}</td>
      <td class="col-frozen" style="left:40px;"><input type="checkbox" class="chk-expediente" data-exp="${r.expediente}" ${seleccionados.has(r.expediente) ? "checked" : ""}></td>
      <td class="col-frozen" style="left:72px;">${formatDateTime(r.fecha_apertura_completa)}</td>
      <td class="col-frozen" style="left:212px;">${celdaExpediente(r.expediente)}</td>
      <td class="col-frozen" style="left:312px;">${puntoSemaforo(r.color_semaforo, r.tiempo_semaforo)}</td>
      <td class="col-frozen" style="left:432px;">${escapeHtml(r.cuenta)}</td>
      <td class="col-frozen" style="left:622px;">${escapeHtml(r.tipo_servicio || "")}</td>
      <td class="col-frozen col-frozen-last" style="left:752px;">${escapeHtml(r.tipo_subservicio || "")}</td>
      <td>${escapeHtml(r.nombre_titular || "")}</td>
      <td>${escapeHtml(r.nombre_paciente)}</td>
      <td>${escapeHtml(r.especialidad || "")}</td>
      <td>${escapeHtml(r.entidad || "")}</td>
      <td>${escapeHtml(r.municipio || "")}</td>
      <td>${r.fecha_asignacion_proveedor ? formatDate(r.fecha_asignacion_proveedor) : '<span class="muted">Sin asignar</span>'}</td>
      <td>${r.fecha_cita ? formatDate(r.fecha_cita) : '<span class="muted">Sin cita</span>'}</td>
      <td>${escapeHtml(r.telefono || "")}</td>
      <td>${escapeHtml(r.email || "")}</td>
      <td>${badgeEstatus(r.estatus)}</td>
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
