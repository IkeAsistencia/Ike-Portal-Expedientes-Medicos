/* Tarjeta "Filtros" de los listados de expedientes. Todos los ids llevan el
   prefijo que se indique ("" para Expedientes, "pa-" para Expedientes PA). */
import { multiselectCuentasHtml } from "./multiselect-cuentas.js";

export function filtrosExpedientesHtml({ prefijo, opcionesEstatus, idBuscar, idLimpiar }) {
  const p = prefijo;
  return `
    <div class="card tono-azul">
      <div class="card-header"><h2>Filtros</h2></div>
      <div class="card-body">
        <div class="filters-grid">
          <div class="field">
            <label for="${p}f-expediente">Expediente</label>
            <input type="text" id="${p}f-expediente" inputmode="numeric" autocomplete="off" placeholder="Núm. expediente" title="Número de expediente">
          </div>
          <div class="field">
            <label for="${p}f-fechaInicio">Fecha Inicio</label>
            <input type="date" id="${p}f-fechaInicio">
          </div>
          <div class="field">
            <label for="${p}f-fechaFin">Fecha Fin</label>
            <input type="date" id="${p}f-fechaFin">
          </div>
          <div class="field">
            <label for="${p}f-servicio">Servicio</label>
            <select id="${p}f-servicio"></select>
          </div>
          <div class="field">
            <label for="${p}f-subservicio">Subservicio</label>
            <select id="${p}f-subservicio">
              <option value="">Todos</option>
            </select>
          </div>
          <div class="field" id="${p}f-entidad-field">
            <label for="${p}f-entidad">Entidad</label>
            <select id="${p}f-entidad">
              <option value="">Todas</option>
            </select>
          </div>
          <div class="field field-wide">
            <label>Cuenta (una o varias)</label>
            ${multiselectCuentasHtml(`${p}f-cuentas`)}
          </div>
          <div class="field" id="${p}f-estatus-field">
            <label for="${p}f-estatus">Estado</label>
            <select id="${p}f-estatus">
              <option value="">Todos</option>
              ${opcionesEstatus.map(e => `<option value="${e}">${e}</option>`).join("")}
            </select>
          </div>
        </div>
        <div class="filters-actions">
          <button class="btn btn-primary" id="${idBuscar}">Buscar</button>
          <button class="btn btn-secondary" id="${idLimpiar}">Limpiar</button>
        </div>
      </div>
    </div>`;
}

/* Lee los filtros y arma los parámetros de GET /expedientes. Una búsqueda
   puntual por número de expediente es una clave exacta: no debe importar
   ningún otro criterio (fecha, servicio/subservicio, cuenta). */
export function leerParametrosBusqueda(prefijo, cuentasSeleccionadas) {
  const valor = (id) => document.getElementById(prefijo + id).value;
  const clExpediente = valor("f-expediente");
  const porClave = Boolean(clExpediente);
  return {
    cl_expediente: clExpediente || undefined,
    fecha_inicio: porClave ? undefined : (valor("f-fechaInicio") || undefined),
    fecha_fin: porClave ? undefined : (valor("f-fechaFin") || undefined),
    cl_servicio: porClave ? undefined : (valor("f-servicio") || undefined),
    cl_subservicio: porClave ? undefined : (valor("f-subservicio") || undefined),
    cuentas: porClave ? undefined : (cuentasSeleccionadas.length ? cuentasSeleccionadas : undefined),
  };
}
