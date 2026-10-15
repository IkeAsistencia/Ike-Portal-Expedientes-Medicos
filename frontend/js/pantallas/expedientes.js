/* Pantalla: Expedientes (bandeja principal de Cabina, Proveedor y Administrador). */
import { api } from "../core/api.js";
import { escapeHtml, normalizarEntidad } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { actualizarAlertaPersistente, quitarAlertaPersistente } from "../componentes/alerta-flotante.js";
import { esPerfilAdministrador, esPerfilCabina, esPerfilProveedor } from "../core/sesion.js";
import {
  cargarCatalogoCuentas, cargarCatalogoEntidades, cargarServiciosEnSelect,
  cargarSubserviciosEnSelect, poblarSelectEntidades,
} from "../core/catalogos.js";
import {
  ESTATUS_ACCIONABLES_PROVEEDOR, EVENTO_ESTATUS_CAMBIADO, aplicarFiltroSubservicioLocal,
  establecerSubserviciosPermitidos, estatusDefaultParaPerfil, hoyISO, notificarCambioEstatus,
  pisoFechaInicioISO, proveedorPuedeVer, validarRangoFechas,
} from "../core/reglas-expedientes.js";
import { ICONOS } from "../componentes/iconos.js";
import { kpiHtml } from "../componentes/kpi.js";
import { limitarADigitos } from "../componentes/campo-numerico.js";
import { crearMultiselectCuentas } from "../componentes/multiselect-cuentas.js";
import { filtrosExpedientesHtml, leerParametrosBusqueda } from "../componentes/filtros-expedientes.js";
import { paginar, renderPaginador } from "../componentes/paginador.js";
import { filaMensaje, puntoSemaforo, renderFilasExpedientes, tablaExpedientesHtml } from "../componentes/tabla-expedientes.js";
import { abrirModalCorte } from "./corte.js";
import { abrirSeguimiento, refrescarSiEsElMismo } from "./seguimiento.js";

const PLANTILLA = `
  <div class="notif-banner hidden" id="notif-atendidos">
    ${ICONOS.alerta}
    <span id="notif-atendidos-texto"></span>
    <button class="notif-close" id="notif-atendidos-cerrar" title="Cerrar">✕</button>
  </div>

  <div class="kpi-row">
    ${kpiHtml({ clase: "kpi-total", idTarjeta: "kpi-total-card", idValor: "kpi-total", idEtiqueta: "kpi-total-label", etiqueta: "Total Expedientes", icono: ICONOS.expediente, clicable: true })}
    ${kpiHtml({ clase: "kpi-proceso", idTarjeta: "kpi-proceso-card", idIcono: "kpi-proceso-icon", idValor: "kpi-proceso", idEtiqueta: "kpi-proceso-label", etiqueta: "En Proceso", icono: ICONOS.reloj, clicable: true })}
    ${kpiHtml({ clase: "kpi-seguimiento", idTarjeta: "kpi-seguimiento-card", idValor: "kpi-seguimiento", etiqueta: "Seguimiento Proveedor", icono: ICONOS.lupa, clicable: true, ocultaPorPerfil: true })}
    ${kpiHtml({ clase: "kpi-cita", idTarjeta: "kpi-cita-card", idValor: "kpi-cita", etiqueta: "Seguimiento de Cita", icono: ICONOS.calendario, clicable: true, ocultaPorPerfil: true })}
  </div>

  ${filtrosExpedientesHtml({
    prefijo: "",
    opcionesEstatus: ["Abierto", "En Espera de Respuesta", "Seguimiento Proveedor", "Seguimiento de Cita", "Finalizado"],
    idBuscar: "btn-buscar-expedientes",
    idLimpiar: "btn-limpiar-expedientes",
  })}

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Resultados de la búsqueda</h2>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-secondary" id="btn-generar-corte">Generar corte</button>
        <button class="btn btn-primary" id="btn-enviar-correo-proveedores">Enviar correo a proveedores</button>
      </div>
    </div>
    <div class="semaforo-panel">
    <div class="semaforo-filtro" id="semaforo-filtro">
      <span class="semaforo-filtro-titulo">Filtrar por semáforo</span>
      <button type="button" class="semaforo-btn" data-color="verde" title="Ver solo los expedientes en tiempo"><i class="semaforo-punto verde"></i>En tiempo <b id="semaforo-n-verde">0</b></button>
      <button type="button" class="semaforo-btn" data-color="amarillo" title="Ver solo los expedientes por vencer" id="semaforo-btn-amarillo"><i class="semaforo-punto amarillo"></i>Por vencer <b id="semaforo-n-amarillo">0</b></button>
      <button type="button" class="semaforo-btn" data-color="naranja" title="Ver solo los expedientes urgentes"><i class="semaforo-punto naranja"></i>Urgente <b id="semaforo-n-naranja">0</b></button>
      <button type="button" class="semaforo-btn" data-color="rojo" title="Ver solo los expedientes vencidos"><i class="semaforo-punto rojo"></i>Vencido <b id="semaforo-n-rojo">0</b></button>
      <button type="button" class="btn-link-semaforo hidden" id="semaforo-quitar">Quitar filtro</button>
    </div>
    <details class="semaforo-leyenda" open>
      <summary>⏱ Semáforo de tiempos</summary>
      <div class="semaforo-grid">
        <div class="semaforo-fila" id="semaforo-filas-sin-escalar">
          <div class="semaforo-grupo"><strong>Primer contacto</strong><span>Sin escalar a proveedor</span></div>
          <span class="semaforo-chip"><i class="semaforo-punto verde"></i>&lt; 6 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto amarillo"></i>6 – 12 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto naranja"></i>12 – 24 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto rojo"></i>&gt; 24 h</span>
          <div class="semaforo-grupo"><strong>Segundo contacto</strong><span>Sin escalar a proveedor</span></div>
          <span class="semaforo-chip"><i class="semaforo-punto verde"></i>&lt; 12 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto amarillo"></i>12 – 48 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto naranja"></i>48 – 72 h</span>
          <span class="semaforo-chip"><i class="semaforo-punto rojo"></i>&gt; 72 h</span>
        </div>
        <div class="semaforo-grupo"><strong>Escalado a proveedor</strong><span>Tiempo sin respuesta</span></div>
        <span class="semaforo-chip"><i class="semaforo-punto verde"></i>≤ 120 min</span>
        <span class="semaforo-vacio"></span>
        <span class="semaforo-chip"><i class="semaforo-punto naranja"></i>120 – 180 min</span>
        <span class="semaforo-chip"><i class="semaforo-punto rojo"></i>&gt; 180 min (vencido)</span>
      </div>
    </details>
    </div>
    <div class="table-wrap table-wrap-listado">
      ${tablaExpedientesHtml({
        idTabla: "tabla-expedientes",
        idChkTodos: "chk-todos",
        idTbody: "tabla-expedientes-body",
        mensajeInicial: "Inicia sesión y presiona Buscar para cargar expedientes.",
      })}
    </div>
    <div class="pager" id="expedientes-pager"></div>
  </div>`;

const INTERVALO_POLLING_MS = 20000; // 20s: se sienta "en vivo" sin saturar al servidor

let expedientesActuales = [];
const seleccionados = new Set();
let paginaActual = 1;
let msCuentas = null;

// Al hacer clic en un KPI, se guarda aquí qué estatus(es) representa esa
// tarjeta y se usa como filtro -- sin necesitar que el combo "Estado" tenga
// una opción exacta para cada KPI (ej. "En Proceso" es dos estatus a la vez).
let filtroEstatusKPI = null;

// Color del semáforo elegido en la barra "Filtrar por semáforo" (null = todos).
let filtroSemaforo = null;
const COLORES_SEMAFORO = ["verde", "amarillo", "naranja", "rojo"];

// Guarda la última búsqueda que el usuario realmente mandó (con "Buscar" o
// al entrar a la pantalla), para que el refresco silencioso en segundo
// plano (ver iniciarPolling) repita EXACTAMENTE esa búsqueda sin importar
// qué esté a medio escribir en los campos del filtro en ese momento.
let ultimaBusquedaParams = null;
let pollingId = null;

// Qué expedientes estaban visibles en pantalla la última vez que se revisó,
// y con qué estatus (ver notificarExpedientesNuevos) -- null = todavía no
// hay una base con qué comparar (primera carga), para no avisar "nuevos" de
// algo que en realidad el usuario está viendo por primera vez.
let estatusVisiblesAnteriores = null;

// Para "el proveedor respondió" (ver notificarRespuestaProveedor) hace falta
// una base APARTE, sin el filtro de "Estado" aplicado: Cabina normalmente
// tiene la tabla filtrada en "Abierto", y un expediente que ya le mandó al
// proveedor vive en "En Espera de Respuesta" -> "Seguimiento Proveedor" --
// ninguno de los dos aparece en "Abierto", así que si solo se comparara
// contra lo filtrado (estatusVisiblesAnteriores), ese cambio nunca se vería.
let estatusTodosAnteriores = null;

// Expedientes con respuesta del proveedor que Cabina todavía no revisa --
// se acumulan aquí (en vez de desaparecer solos) y solo se quitan cuando el
// expediente deja de estar en "Seguimiento Proveedor" (reconciliarRespuestasPendientes).
const respuestasPendientes = new Map();
const ID_ALERTA_RESPUESTAS = "alerta-respuestas-proveedor";

const $ = (id) => document.getElementById(id);

/* ---------- Filtros locales (sobre lo que ya trajo la búsqueda) ---------- */
function aplicarFiltroEstatusLocal(rows) {
  // Proveedor no tiene el combo "Estado" (queda oculto/fijo), pero sí puede
  // darle clic a sus dos KPI para ver solo "En Espera de Respuesta" o solo
  // "Seguimiento de Cita" -- sin filtro de KPI activo, ve su bandeja completa.
  if (esPerfilProveedor()) {
    const permitido = filtroEstatusKPI || ESTATUS_ACCIONABLES_PROVEEDOR;
    return rows.filter(r => permitido.includes(r.estatus));
  }
  if (filtroEstatusKPI) {
    return rows.filter(r => filtroEstatusKPI.includes(r.estatus));
  }
  const val = $("f-estatus").value;
  if (!val) return rows;
  return rows.filter(r => r.estatus === val);
}

function aplicarFiltroEntidadLocal(rows) {
  const val = $("f-entidad").value;
  if (!val) return rows;
  const valNormalizado = normalizarEntidad(val);
  return rows.filter(r => normalizarEntidad(r.entidad) === valNormalizado);
}

function aplicarFiltroSemaforoLocal(rows) {
  return filtroSemaforo ? rows.filter(r => r.color_semaforo === filtroSemaforo) : rows;
}

// Lo que se ve en la tabla ANTES de filtrar por color: de aquí salen los
// contadores del semáforo, para que cada número diga cuántos hay de ese color
// en la vista actual (mismo Estado/Subservicio/Entidad).
function filasSinFiltroSemaforo(rows) {
  return aplicarFiltroEntidadLocal(aplicarFiltroSubservicioLocal(aplicarFiltroEstatusLocal(rows)));
}

function aplicarFiltrosLocales(rows) {
  return aplicarFiltroSemaforoLocal(filasSinFiltroSemaforo(rows));
}

/* ---------- Semáforo: contadores y filtro por color ---------- */
function renderSemaforoResumen(base) {
  const cuenta = { verde: 0, amarillo: 0, naranja: 0, rojo: 0 };
  base.forEach(r => { if (r.color_semaforo in cuenta) cuenta[r.color_semaforo]++; });
  COLORES_SEMAFORO.forEach(c => { $("semaforo-n-" + c).textContent = cuenta[c]; });
  document.querySelectorAll("#semaforo-filtro .semaforo-btn").forEach(b => {
    b.classList.toggle("activo", b.dataset.color === filtroSemaforo);
  });
  $("semaforo-quitar").classList.toggle("hidden", !filtroSemaforo);
}

function filtrarPorSemaforo(color) {
  filtroSemaforo = color && color !== filtroSemaforo ? color : null;
  paginaActual = 1;
  // Igual que al cambiar de Estado o usar un KPI: no dejar seleccionado algo
  // que quedó fuera del filtro.
  seleccionados.clear();
  $("chk-todos").checked = false;
  const filtrados = aplicarFiltrosLocales(expedientesActuales);
  actualizarBaselineVisibles(filtrados);
  renderTabla(filtrados);
  renderSemaforoResumen(filasSinFiltroSemaforo(expedientesActuales));
}

function datosResumenPerfil() {
  // Para KPIs y avisos: todo lo que trajo la búsqueda actual (respeta el
  // filtro temporal de subservicios), SIN aplicar el filtro de "Estado" de
  // la tabla — así el resumen no cambia solo porque estés viendo otro Estado.
  return aplicarFiltroSubservicioLocal(expedientesActuales);
}

/* ---------- KPIs ---------- */
function marcarKpiActivo(cardId) {
  document.querySelectorAll("#screen-expedientes .kpi-card.kpi-clickable").forEach(el => {
    el.classList.toggle("kpi-activo", el.id === cardId);
  });
}

function filtrarPorKPI(cardId, estatusList, valorCombo) {
  filtroEstatusKPI = estatusList;
  $("f-estatus").value = valorCombo || "";
  paginaActual = 1;
  // Mismo motivo que en loadExpedientes(): no dejar seleccionado algo que
  // quedó fuera de este filtro (de otro estado).
  seleccionados.clear();
  $("chk-todos").checked = false;
  marcarKpiActivo(cardId);
  const filtrados = aplicarFiltrosLocales(expedientesActuales);
  // Para que el siguiente refresco silencioso compare contra lo que se ve
  // AHORA (con este filtro de KPI), y no avise "nuevos" solo porque cambió
  // el filtro en vez de haber llegado algo de verdad.
  actualizarBaselineVisibles(filtrados);
  renderTabla(filtrados);
  renderSemaforoResumen(filasSinFiltroSemaforo(expedientesActuales));
  renderKPIs();
  $("tabla-expedientes").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderKPIs() {
  const rows = datosResumenPerfil();
  const contar = (estatus) => rows.filter(r => r.estatus === estatus).length;
  if (esPerfilProveedor()) {
    // Sus dos tipos de pendientes: los que le mandaron a él y los que ya
    // regresó Cabina con la cita aceptada (pago anticipado).
    $("kpi-total").textContent = contar("En Espera de Respuesta");
    $("kpi-proceso").textContent = contar("Seguimiento de Cita");
    return;
  }
  if (esPerfilCabina()) {
    $("kpi-total").textContent = contar("Abierto");
    $("kpi-proceso").textContent = contar("En Espera de Respuesta");
    $("kpi-seguimiento").textContent = contar("Seguimiento Proveedor");
    $("kpi-cita").textContent = contar("Seguimiento de Cita");
    return;
  }
  // Perfil sin reglas propias todavía (ej. Administrador): comportamiento genérico.
  $("kpi-total").textContent = rows.length;
  $("kpi-proceso").textContent =
    rows.filter(r => ["En Espera de Respuesta", "Seguimiento Proveedor"].includes(r.estatus)).length;
}

function aplicarEtiquetasKPI() {
  const tarjetaProceso = $("kpi-proceso-card");
  const iconoProceso = $("kpi-proceso-icon");
  if (esPerfilProveedor()) {
    $("kpi-total-label").textContent = "En Espera de Respuesta";
    $("kpi-proceso-label").textContent = "Seguimiento de Cita";
    // Mismo color/ícono que la tarjeta "Seguimiento de Cita" de Cabina --
    // el mismo concepto debe verse igual sin importar el perfil.
    tarjetaProceso.classList.add("kpi-estilo-cita");
    iconoProceso.innerHTML = ICONOS.calendario;
  } else {
    tarjetaProceso.classList.remove("kpi-estilo-cita");
    iconoProceso.innerHTML = ICONOS.reloj;
    if (esPerfilCabina()) {
      $("kpi-total-label").textContent = "Expedientes sin asignar";
      $("kpi-proceso-label").textContent = "En espera de respuesta";
    } else {
      $("kpi-total-label").textContent = "Total Expedientes";
      $("kpi-proceso-label").textContent = "En Proceso";
    }
  }
}

function actualizarNotificacionAtendidos() {
  const banner = $("notif-atendidos");
  if (!esPerfilCabina()) {
    // Este aviso es para que Cabina revise lo que ya respondió el proveedor;
    // a Proveedor no le corresponde (su bandeja ya está limitada a "En Espera de Respuesta").
    banner.classList.add("hidden");
    return;
  }
  const enSeguimiento = datosResumenPerfil().filter(r => r.estatus === "Seguimiento Proveedor").length;
  if (enSeguimiento > 0) {
    $("notif-atendidos-texto").textContent =
      `Hay ${enSeguimiento} expediente${enSeguimiento === 1 ? "" : "s"} en seguimiento con el proveedor que debe${enSeguimiento === 1 ? "" : "n"} revisarse.`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

/* ---------- Tabla ---------- */
function renderTabla(rows) {
  const tbody = $("tabla-expedientes-body");
  const pag = paginar(rows, paginaActual);
  paginaActual = pag.pagina;

  if (!rows.length) {
    filaMensaje(tbody, "No se encontraron expedientes con estos filtros.");
  } else {
    renderFilasExpedientes(tbody, pag.filas, {
      inicio: pag.inicio,
      seleccionados,
      alAbrir: (exp) => {
        const rec = expedientesActuales.find(x => x.expediente === exp);
        if (rec) abrirSeguimiento(rec, "link");
      },
      alCambiarSeleccion: () => {
        $("chk-todos").checked = rows.length > 0 && rows.every(r => seleccionados.has(r.expediente));
      },
    });
  }

  renderPaginador($("expedientes-pager"), {
    totalFilas: rows.length,
    pagina: paginaActual,
    totalPaginas: pag.totalPaginas,
    alCambiar: (nueva) => {
      paginaActual = nueva;
      renderTabla(aplicarFiltrosLocales(expedientesActuales));
    },
  });
}

/* Vuelve a pintar todo con lo que ya está en memoria, sin ir al servidor. */
function refrescarVista() {
  renderTabla(aplicarFiltrosLocales(expedientesActuales));
  renderSemaforoResumen(filasSinFiltroSemaforo(expedientesActuales));
  renderKPIs();
  actualizarNotificacionAtendidos();
}

/* ---------- Búsqueda ---------- */
async function cargarServiciosFiltro() {
  const servicios = await cargarServiciosEnSelect($("f-servicio"));
  if (servicios.length) await cargarSubservicios(servicios[0].clave);
}

async function cargarCuentasFiltro() {
  await cargarCatalogoCuentas({ forzar: true });
  msCuentas.renderizar();
}

async function cargarSubservicios(clServicio) {
  const subservicios = await cargarSubserviciosEnSelect($("f-subservicio"), clServicio);
  // Filtro temporal: solo se trabaja con los subservicios de este catálogo (acordado con el equipo).
  if (subservicios) establecerSubserviciosPermitidos(subservicios);
}

async function actualizarOpcionesEntidad() {
  await cargarCatalogoEntidades();
  poblarSelectEntidades($("f-entidad"), "Todas");
}

async function loadExpedientes() {
  // Búsqueda puntual por número de expediente: no debe importar la regla
  // de fechas, es una clave exacta -- se manda sin acotar por fecha.
  if (!$("f-expediente").value) {
    const errorRango = validarRangoFechas($("f-fechaInicio").value, $("f-fechaFin").value);
    if (errorRango) {
      toast(errorRango, "error");
      return;
    }
  }

  const params = leerParametrosBusqueda("", msCuentas.seleccionadas());
  ultimaBusquedaParams = params;
  // Una búsqueda explícita (clic en "Buscar") manda sobre cualquier filtro
  // rápido que se haya activado antes haciendo clic en un KPI.
  filtroEstatusKPI = null;
  filtroSemaforo = null;
  marcarKpiActivo(null);
  paginaActual = 1;
  // Limpia la selección: si no, quedan marcados expedientes de un estado
  // distinto al que acabas de buscar (ej. seleccionaste "Abierto", ahora
  // buscas "Finalizado") y el corte/correo truena por mezclar estados.
  seleccionados.clear();
  $("chk-todos").checked = false;

  filaMensaje($("tabla-expedientes-body"), "Cargando…", "spinner-row");
  await ejecutarBusqueda(params, { silencioso: false });
}

function actualizarBaselineVisibles(filtrados) {
  estatusVisiblesAnteriores = new Map(filtrados.map(r => [r.expediente, r.estatus]));
}

function actualizarBaselineTodos(data) {
  estatusTodosAnteriores = new Map(data.map(r => [r.expediente, r.estatus]));
}

function notificarExpedientesNuevos(nuevos) {
  const numeros = nuevos.map(r => r.expediente);
  const mensaje = numeros.length === 1
    ? `Nuevo expediente: ${numeros[0]}.`
    : numeros.length <= 4
      ? `Llegaron ${numeros.length} expedientes nuevos: ${numeros.join(", ")}.`
      : `Llegaron ${numeros.length} expedientes nuevos.`;
  // Un poco más de tiempo que el toast normal (4s) -- que a uno le dé
  // tiempo de notar que llegó algo, sin quedarse pegado en pantalla.
  toast(mensaje, "success", 6000);
}

// Aviso a Cabina cuando un Proveedor responde (el expediente ya estaba en
// pantalla, pero cambió a "Seguimiento Proveedor"). Además del cambio de
// estatus que ya se ve en la tabla, se pidió una alerta aparte (sección 1
// de "Puntos a modificar.docx"): esquina superior derecha, en naranja (para
// diferenciarla de otros tipos de alerta), con el número de expediente como
// liga -- igual que en la tabla, abre directo su Seguimiento. A diferencia
// del primer diseño, ahora NO se quita sola: los expedientes se van
// acumulando en la misma alerta hasta que Cabina le cambia el estatus (ver
// reconciliarRespuestasPendientes), y cada uno muestra también el nombre
// del paciente y su semáforo.
function notificarRespuestaProveedor(respondidos) {
  const numeros = respondidos.map(r => r.expediente);
  const mensajeToast = numeros.length === 1
    ? `El proveedor respondió: expediente ${numeros[0]}.`
    : numeros.length <= 4
      ? `El proveedor respondió ${numeros.length} expedientes: ${numeros.join(", ")}.`
      : `El proveedor respondió ${numeros.length} expedientes.`;
  toast(mensajeToast, "success", 6000);

  respondidos.forEach(r => {
    respuestasPendientes.set(r.expediente, {
      expediente: r.expediente,
      nombre_paciente: r.nombre_paciente,
      color_semaforo: r.color_semaforo,
      tiempo_semaforo: r.tiempo_semaforo,
    });
    // Si Cabina tiene abierta la pantalla de Seguimiento justo de este
    // expediente, que se vea de una vez la respuesta que Core acaba de
    // registrar, sin esperar a que alguien lo busque de nuevo a mano.
    refrescarSiEsElMismo(r.expediente);
  });
  renderAlertaRespuestasPendientes({ sonar: true });
}

// Quita de la alerta acumulada cualquier expediente que ya no esté en
// "Seguimiento Proveedor" (porque Cabina lo revisó y le cambió el estatus) o
// que ya no venga en la respuesta del servidor. Solo tiene sentido correrlo
// con una búsqueda que trae TODO (sin acotar por número de expediente).
function reconciliarRespuestasPendientes(data) {
  if (respuestasPendientes.size === 0) return;
  const porExpediente = new Map(data.map(r => [r.expediente, r]));
  let cambio = false;
  for (const exp of Array.from(respuestasPendientes.keys())) {
    const actual = porExpediente.get(exp);
    if (!actual || actual.estatus !== "Seguimiento Proveedor") {
      respuestasPendientes.delete(exp);
      cambio = true;
    }
  }
  if (cambio) renderAlertaRespuestasPendientes({ sonar: false });
}

// Un usuario de Cabina "toma" un expediente de la alerta en cuanto le
// cambia el estatus (lo revisó y avanzó el caso) -- se quita de inmediato en
// esta misma sesión, sin esperar al siguiente refresco silencioso (hasta
// 20s). Para las demás sesiones de Cabina que tengan ese mismo expediente
// pendiente, el siguiente refresco (reconciliarRespuestasPendientes) lo
// quita igual, así no queda abierto para que alguien más lo tome también.
function quitarDeRespuestasPendientesSiYaNoAplica(expediente, estatus) {
  if (!respuestasPendientes.has(expediente) || estatus === "Seguimiento Proveedor") return;
  respuestasPendientes.delete(expediente);
  renderAlertaRespuestasPendientes({ sonar: false });
}

function renderAlertaRespuestasPendientes({ sonar }) {
  if (respuestasPendientes.size === 0) {
    quitarAlertaPersistente(ID_ALERTA_RESPUESTAS);
    return;
  }
  const pendientes = Array.from(respuestasPendientes.values());
  const titulo = pendientes.length === 1
    ? "El proveedor respondió 1 expediente:"
    : `El proveedor respondió ${pendientes.length} expedientes:`;
  const items = pendientes.map(p => `
    <li class="alerta-flotante-item">
      <a href="#" class="alerta-flotante-link" data-exp="${p.expediente}">${p.expediente}</a>
      <span class="alerta-flotante-paciente">${escapeHtml(p.nombre_paciente || "")}</span>
      ${puntoSemaforo(p.color_semaforo, p.tiempo_semaforo)}
    </li>`).join("");
  const mensajeHtml = `${titulo}<ul class="alerta-flotante-lista">${items}</ul>`;

  actualizarAlertaPersistente(ID_ALERTA_RESPUESTAS, mensajeHtml, {
    tipo: "proveedor-respondio",
    sonar,
    colapsable: true,
    alClicLink: (exp) => {
      const rec = expedientesActuales.find(x => x.expediente === exp);
      if (rec) abrirSeguimiento(rec, "link");
    },
  });
}

async function ejecutarBusqueda(params, { silencioso }) {
  try {
    const data = await api("/expedientes", { params });
    data.sort((a, b) => a.fecha_apertura_servicio.localeCompare(b.fecha_apertura_servicio));
    expedientesActuales = data;
    actualizarOpcionesEntidad();
    // Igual que con las fechas: al buscar por clave, tampoco se aplican los
    // filtros locales (Estado/Subservicio/Entidad) -- se muestra tal cual.
    // Excepción: Proveedor solo puede ver "En Espera de Respuesta" o
    // "Seguimiento Proveedor" (los suyos), sin importar la clave buscada.
    const filtrados = params.cl_expediente ? data.filter(r => proveedorPuedeVer(r.estatus)) : aplicarFiltrosLocales(data);

    // Avisar de expedientes nuevos SOLO en el refresco silencioso (no en una
    // búsqueda que el propio usuario acaba de pedir) y solo si ya había algo
    // con qué comparar (si no, sería la primera vez que ve esta pantalla).
    if (silencioso && estatusVisiblesAnteriores) {
      const nuevos = filtrados.filter(r => !estatusVisiblesAnteriores.has(r.expediente));
      if (nuevos.length > 0) notificarExpedientesNuevos(nuevos);
    }

    // Aparte del filtro de Estado: Cabina normalmente ve la tabla en
    // "Abierto", pero el expediente ya vive en otro estado para cuando el
    // proveedor responde -- hay que buscar el cambio en TODO lo que trajo la
    // búsqueda (data), no solo en lo que está filtrado en pantalla (filtrados).
    if (silencioso && estatusTodosAnteriores && (esPerfilCabina() || esPerfilAdministrador())) {
      const respondidos = data.filter(r =>
        r.estatus === "Seguimiento Proveedor" &&
        estatusTodosAnteriores.has(r.expediente) &&
        estatusTodosAnteriores.get(r.expediente) !== "Seguimiento Proveedor"
      );
      if (respondidos.length > 0) notificarRespuestaProveedor(respondidos);
    }
    if (!params.cl_expediente && (esPerfilCabina() || esPerfilAdministrador())) {
      reconciliarRespuestasPendientes(data);
    }
    actualizarBaselineVisibles(filtrados);
    actualizarBaselineTodos(data);

    renderTabla(filtrados);
    renderSemaforoResumen(params.cl_expediente ? filtrados : filasSinFiltroSemaforo(data));
    renderKPIs();
    actualizarNotificacionAtendidos();
  } catch (err) {
    if (silencioso) {
      console.warn("No se pudo refrescar Expedientes en segundo plano:", err.message);
      return;
    }
    filaMensaje($("tabla-expedientes-body"), escapeHtml(err.message));
    toast(err.message, "error");
  }
}

/* Para que a Proveedor le vayan apareciendo solos los expedientes nuevos
   que Cabina le mande (y a Cabina/Admin se les actualice lo que ya ven)
   mientras tengan el portal abierto, sin que nadie tenga que refrescar. */
export function iniciarPolling() {
  if (pollingId) return; // ya está corriendo
  pollingId = setInterval(() => {
    if (!ultimaBusquedaParams) return; // todavía no se ha hecho ninguna búsqueda
    ejecutarBusqueda(ultimaBusquedaParams, { silencioso: true });
  }, INTERVALO_POLLING_MS);
}

function detenerPolling() {
  if (!pollingId) return;
  clearInterval(pollingId);
  pollingId = null;
  ultimaBusquedaParams = null;
}

/* ---------- Acciones ---------- */
async function enviarCorreoProveedores() {
  if (seleccionados.size === 0) {
    toast("Selecciona al menos un expediente antes de enviar el correo.", "error");
    return;
  }
  const btn = $("btn-enviar-correo-proveedores");
  btn.disabled = true;
  try {
    const data = await api("/expedientes/enviar-correo-proveedores", {
      method: "POST",
      body: { expedientes: Array.from(seleccionados) },
    });
    toast(`Correo enviado para ${data.enviados} expediente(s).`, "success");
    seleccionados.clear();
    $("chk-todos").checked = false;
    // El envío marca automáticamente esos expedientes como "En Espera de
    // Respuesta" -- el evento lo refleja aquí (ver montar) y en Expedientes PA.
    data.expedientes.forEach(exp => notificarCambioEstatus(exp, "En Espera de Respuesta"));
    refrescarVista();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function limpiarFiltros() {
  $("f-expediente").value = "";
  $("f-fechaInicio").value = "";
  $("f-fechaFin").value = "";
  $("f-estatus").value = esPerfilProveedor() ? "En Espera de Respuesta" : "";
  $("f-subservicio").value = "";
  $("f-entidad").value = "";
  msCuentas.limpiar();
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  msCuentas = crearMultiselectCuentas("f-cuentas");
  limitarADigitos($("f-expediente"));

  $("semaforo-filtro").addEventListener("click", (e) => {
    if (e.target.closest("#semaforo-quitar")) { filtrarPorSemaforo(null); return; }
    const btn = e.target.closest(".semaforo-btn");
    if (btn) filtrarPorSemaforo(btn.dataset.color);
  });
  $("notif-atendidos-cerrar").addEventListener("click", () => $("notif-atendidos").classList.add("hidden"));

  $("kpi-total-card").addEventListener("click", () => {
    if (esPerfilCabina()) filtrarPorKPI("kpi-total-card", ["Abierto"], "Abierto");
    else if (esPerfilProveedor()) filtrarPorKPI("kpi-total-card", ["En Espera de Respuesta"], "En Espera de Respuesta");
    else filtrarPorKPI("kpi-total-card", null, ""); // Administrador: "Total" = sin filtro
  });
  $("kpi-proceso-card").addEventListener("click", () => {
    if (esPerfilCabina()) filtrarPorKPI("kpi-proceso-card", ["En Espera de Respuesta"], "En Espera de Respuesta");
    else if (esPerfilProveedor()) filtrarPorKPI("kpi-proceso-card", ["Seguimiento de Cita"], "Seguimiento de Cita");
    else filtrarPorKPI("kpi-proceso-card", ["En Espera de Respuesta", "Seguimiento Proveedor"], "");
  });
  $("kpi-seguimiento-card").addEventListener("click", () => {
    filtrarPorKPI("kpi-seguimiento-card", ["Seguimiento Proveedor"], "Seguimiento Proveedor");
  });
  $("kpi-cita-card").addEventListener("click", () => {
    filtrarPorKPI("kpi-cita-card", ["Seguimiento de Cita"], "Seguimiento de Cita");
  });

  $("f-servicio").addEventListener("change", (e) => cargarSubservicios(e.target.value));
  $("btn-buscar-expedientes").addEventListener("click", loadExpedientes);
  contenedor.querySelector(".filters-grid").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && !e.target.closest(".ms-panel")) {
      e.preventDefault();
      loadExpedientes();
    }
  });
  $("btn-limpiar-expedientes").addEventListener("click", () => {
    limpiarFiltros();
    seleccionados.clear();
    loadExpedientes();
  });

  $("chk-todos").addEventListener("change", (e) => {
    const filas = aplicarFiltrosLocales(expedientesActuales);
    filas.forEach(r => {
      if (e.target.checked) seleccionados.add(r.expediente);
      else seleccionados.delete(r.expediente);
    });
    renderTabla(filas);
  });

  $("btn-enviar-correo-proveedores").addEventListener("click", enviarCorreoProveedores);
  $("btn-generar-corte").addEventListener("click", () => abrirModalCorte({
    tipoExpediente: "normal",
    seleccionados,
    fuente: expedientesActuales,
    boton: $("btn-generar-corte"),
    alConfirmar: () => {
      seleccionados.clear();
      $("chk-todos").checked = false;
      renderTabla(aplicarFiltrosLocales(expedientesActuales));
    },
  }));

  // Otra pantalla (Seguimiento, Expedientes PA) cambió el estatus de un expediente.
  document.addEventListener(EVENTO_ESTATUS_CAMBIADO, (e) => {
    const rec = expedientesActuales.find(r => r.expediente === e.detail.expediente);
    if (!rec) return;
    rec.estatus = e.detail.estatus;
    quitarDeRespuestasPendientesSiYaNoAplica(e.detail.expediente, e.detail.estatus);
    refrescarVista();
  });
}

export function aplicarPermisos() {
  const cabina = esPerfilCabina();
  const proveedor = esPerfilProveedor();
  const admin = esPerfilAdministrador();

  // Proveedor no filtra por Estado: su vista queda fija en "En Espera de Respuesta".
  $("f-estatus-field").classList.toggle("hidden-perfil", proveedor);
  // Filtro por Entidad: solo para Proveedor.
  $("f-entidad-field").classList.toggle("hidden-perfil", !proveedor);

  // Enviar correo a proveedores es una acción operativa de Cabina --
  // Administrador ya no la usa (ver nota de "Generar corte" abajo).
  $("btn-enviar-correo-proveedores").classList.toggle("hidden-perfil", proveedor || admin);
  // Generar corte quedó exclusivo del perfil Administrador (decisión del
  // jefe): Cabina y Proveedor ya no lo ven.
  $("btn-generar-corte").classList.toggle("hidden-perfil", proveedor || cabina);

  // Semáforo: Proveedor solo ve la leyenda de "Escalado a proveedor"; los
  // tiempos de "sin escalar" (primer y segundo contacto) son de Cabina.
  $("semaforo-filas-sin-escalar").classList.toggle("hidden-perfil", proveedor);
  // Su semáforo (solo "escalado") no tiene amarillo.
  $("semaforo-btn-amarillo").classList.toggle("hidden-perfil", proveedor);

  // KPIs adicionales "Seguimiento Proveedor" y "Seguimiento de Cita", solo para Cabina.
  $("kpi-seguimiento-card").classList.toggle("hidden-perfil", !cabina);
  $("kpi-cita-card").classList.toggle("hidden-perfil", !cabina);

  aplicarEtiquetasKPI();
}

export function alEntrar() {
  $("f-expediente").focus();
  if (expedientesActuales.length > 0) {
    // Refresca la tabla con lo que ya tengamos en memoria (por si algo cambió,
    // como un estatus, mientras estabas en otra pantalla) sin pedirle nada al servidor.
    refrescarVista();
    return;
  }
  // Primera vez que se entra en esta sesión: arranca con los defaults.
  $("f-estatus").value = estatusDefaultParaPerfil();
  $("f-fechaInicio").value = pisoFechaInicioISO();
  $("f-fechaFin").value = hoyISO();
  cargarServiciosFiltro();
  cargarCuentasFiltro();
  loadExpedientes();
}

/* Al cerrar sesión: sin esto, los datos/filtros de la sesión anterior (ej.
   Cabina viendo "Abierto") quedaban en memoria y se alcanzaban a ver un
   instante al iniciar sesión con OTRO perfil (ej. Proveedor). */
export function reiniciar() {
  detenerPolling();
  expedientesActuales = [];
  seleccionados.clear();
  paginaActual = 1;
  filtroEstatusKPI = null;
  filtroSemaforo = null;
  estatusVisiblesAnteriores = null;
  estatusTodosAnteriores = null;
  respuestasPendientes.clear();
  quitarAlertaPersistente(ID_ALERTA_RESPUESTAS);
  limpiarFiltros();
  $("f-estatus").value = "";
  $("tabla-expedientes-body").innerHTML = "";
}
