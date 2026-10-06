/* Pantalla: Expedientes PA (pago anticipado).
   TEMPORAL: jala los mismos datos que "Expedientes" (mismo
   dbo.ObtenerExpedientesSinProveedorMedico) -- todavía no existe en SISE un
   campo/consulta que distinga cuáles son de pago anticipado.
   Hoy está oculta para todos los perfiles (ver pantallaPermitida en app.js):
   el flujo de pago anticipado ya vive dentro de Expedientes. */
import { api } from "../core/api.js";
import { escapeHtml } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { esPerfilAdministrador, esPerfilCabina, esPerfilProveedor } from "../core/sesion.js";
import {
  cargarCatalogoCuentas, cargarCatalogoEntidades, cargarServiciosEnSelect,
  cargarSubserviciosEnSelect, poblarSelectEntidades,
} from "../core/catalogos.js";
import {
  EVENTO_ESTATUS_CAMBIADO, aplicarFiltroSubservicioLocal, estatusDefaultParaPerfil, hoyISO,
  notificarCambioEstatus, pisoFechaInicioISO, proveedorPuedeVer, validarRangoFechas,
} from "../core/reglas-expedientes.js";
import { ICONOS } from "../componentes/iconos.js";
import { kpiHtml } from "../componentes/kpi.js";
import { crearMultiselectCuentas } from "../componentes/multiselect-cuentas.js";
import { filtrosExpedientesHtml, leerParametrosBusqueda } from "../componentes/filtros-expedientes.js";
import { paginar, renderPaginador } from "../componentes/paginador.js";
import { filaMensaje, renderFilasExpedientes, tablaExpedientesHtml } from "../componentes/tabla-expedientes.js";
import { abrirModalCorte } from "./corte.js";
import { abrirSeguimiento } from "./seguimiento.js";

const PLANTILLA = `
  <div class="notif-banner hidden" id="pa-notif-atendidos">
    ${ICONOS.alerta}
    <span id="pa-notif-atendidos-texto"></span>
    <button class="notif-close" id="pa-notif-atendidos-cerrar" title="Cerrar">✕</button>
  </div>

  <div class="kpi-row">
    ${kpiHtml({ clase: "kpi-total", idValor: "pa-kpi-total", idEtiqueta: "pa-kpi-total-label", etiqueta: "Total", icono: ICONOS.tarjeta })}
    ${kpiHtml({ clase: "kpi-proceso", idValor: "pa-kpi-proceso", idEtiqueta: "pa-kpi-proceso-label", etiqueta: "En Proceso", icono: ICONOS.reloj })}
    ${kpiHtml({ clase: "kpi-seguimiento", idTarjeta: "pa-kpi-seguimiento-card", idValor: "pa-kpi-seguimiento", etiqueta: "Seguimiento Proveedor", icono: ICONOS.lupa, ocultaPorPerfil: true })}
  </div>

  ${filtrosExpedientesHtml({
    prefijo: "pa-",
    opcionesEstatus: ["Abierto", "En Espera de Respuesta", "Seguimiento Proveedor", "Finalizado"],
    idBuscar: "pa-btn-buscar",
    idLimpiar: "pa-btn-limpiar",
  })}

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Resultados</h2>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-secondary" id="pa-btn-generar-corte">Generar corte</button>
        <button class="btn btn-primary" id="pa-btn-enviar-correo-proveedores">Enviar correo a proveedores</button>
      </div>
    </div>
    <div class="table-wrap table-wrap-listado">
      ${tablaExpedientesHtml({
        idTabla: "pa-tabla",
        idChkTodos: "pa-chk-todos",
        idTbody: "pa-tabla-body",
        mensajeInicial: "Presiona Buscar para cargar expedientes.",
      })}
    </div>
    <div class="pager" id="pa-pager"></div>
  </div>`;

let expedientesActuales = [];
const seleccionados = new Set();
let paginaActual = 1;
let msCuentas = null;

const $ = (id) => document.getElementById(id);

/* ---------- Filtros locales ---------- */
function aplicarFiltrosLocales(rows) {
  const estatus = $("pa-f-estatus").value;
  const entidad = $("pa-f-entidad").value;
  let filtrados = estatus ? rows.filter(r => r.estatus === estatus) : rows;
  filtrados = aplicarFiltroSubservicioLocal(filtrados);
  return entidad ? filtrados.filter(r => (r.entidad || "") === entidad) : filtrados;
}

function datosResumenPerfil() {
  return aplicarFiltroSubservicioLocal(expedientesActuales);
}

/* ---------- KPIs y aviso ---------- */
function aplicarEtiquetasKPI() {
  if (esPerfilProveedor()) {
    $("pa-kpi-total-label").textContent = "Esperando tu respuesta";
    $("pa-kpi-proceso-label").textContent = "Con más de 1 día esperando";
  } else if (esPerfilCabina()) {
    $("pa-kpi-total-label").textContent = "Expedientes sin asignar";
    $("pa-kpi-proceso-label").textContent = "En espera de respuesta";
  } else {
    $("pa-kpi-total-label").textContent = "Total";
    $("pa-kpi-proceso-label").textContent = "En Proceso";
  }
}

function renderKPIs() {
  const rows = datosResumenPerfil();
  if (esPerfilProveedor()) {
    const enEspera = rows.filter(r => r.estatus === "En Espera de Respuesta");
    const hoy = hoyISO();
    $("pa-kpi-total").textContent = enEspera.length;
    $("pa-kpi-proceso").textContent = enEspera.filter(r => r.fecha_apertura_servicio < hoy).length;
    return;
  }
  if (esPerfilCabina()) {
    $("pa-kpi-total").textContent = rows.filter(r => r.estatus === "Abierto").length;
    $("pa-kpi-proceso").textContent = rows.filter(r => r.estatus === "En Espera de Respuesta").length;
    $("pa-kpi-seguimiento").textContent = rows.filter(r => r.estatus === "Seguimiento Proveedor").length;
    return;
  }
  $("pa-kpi-total").textContent = rows.length;
  $("pa-kpi-proceso").textContent =
    rows.filter(r => ["En Espera de Respuesta", "Seguimiento Proveedor"].includes(r.estatus)).length;
}

function actualizarNotificacionAtendidos() {
  const banner = $("pa-notif-atendidos");
  if (!esPerfilCabina()) {
    banner.classList.add("hidden");
    return;
  }
  const enSeguimiento = datosResumenPerfil().filter(r => r.estatus === "Seguimiento Proveedor").length;
  if (enSeguimiento > 0) {
    $("pa-notif-atendidos-texto").textContent =
      `Hay ${enSeguimiento} expediente${enSeguimiento === 1 ? "" : "s"} en seguimiento con el proveedor que debe${enSeguimiento === 1 ? "" : "n"} revisarse.`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

/* ---------- Tabla ---------- */
function renderTabla(rows) {
  const tbody = $("pa-tabla-body");
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
        $("pa-chk-todos").checked = rows.length > 0 && rows.every(r => seleccionados.has(r.expediente));
      },
    });
  }

  renderPaginador($("pa-pager"), {
    totalFilas: rows.length,
    pagina: paginaActual,
    totalPaginas: pag.totalPaginas,
    alCambiar: (nueva) => {
      paginaActual = nueva;
      renderTabla(aplicarFiltrosLocales(expedientesActuales));
    },
  });
}

function refrescarVista() {
  renderTabla(aplicarFiltrosLocales(expedientesActuales));
  renderKPIs();
  actualizarNotificacionAtendidos();
}

/* ---------- Búsqueda ---------- */
async function cargarServiciosFiltro() {
  const select = $("pa-f-servicio");
  if (select.options.length) return;
  const servicios = await cargarServiciosEnSelect(select);
  if (servicios.length) await cargarSubserviciosEnSelect($("pa-f-subservicio"), servicios[0].clave);
}

async function cargarCuentasFiltro() {
  // Reutiliza el mismo catálogo que ya carga "Expedientes" (core/catalogos.js);
  // si por algún motivo entraron directo aquí y todavía no se cargó, lo carga.
  await cargarCatalogoCuentas();
  msCuentas.renderizar();
}

async function loadExpedientes() {
  // Búsqueda puntual por número de expediente: no debe importar la regla
  // de fechas, es una clave exacta -- se manda sin acotar por fecha.
  const clExpediente = $("pa-f-expediente").value;
  if (!clExpediente) {
    const errorRango = validarRangoFechas($("pa-f-fechaInicio").value, $("pa-f-fechaFin").value);
    if (errorRango) { toast(errorRango, "error"); return; }
  }

  const params = leerParametrosBusqueda("pa-", msCuentas.seleccionadas());
  const tbody = $("pa-tabla-body");
  filaMensaje(tbody, "Cargando…", "spinner-row");

  try {
    const data = await api("/expedientes", { params });
    data.sort((a, b) => a.fecha_apertura_servicio.localeCompare(b.fecha_apertura_servicio));
    expedientesActuales = data;
    paginaActual = 1;
    cargarCatalogoEntidades().then(() => poblarSelectEntidades($("pa-f-entidad"), "Todas"));
    // Igual que con las fechas: al buscar por clave, tampoco se aplican los
    // filtros locales (Estado/Subservicio/Entidad) -- se muestra tal cual.
    // Excepción: Proveedor solo puede ver los suyos, sin importar la clave buscada.
    const filtrados = clExpediente ? data.filter(r => proveedorPuedeVer(r.estatus)) : aplicarFiltrosLocales(data);
    renderTabla(filtrados);
    renderKPIs();
    actualizarNotificacionAtendidos();
  } catch (err) {
    filaMensaje(tbody, escapeHtml(err.message));
    toast(err.message, "error");
  }
}

async function enviarCorreoProveedores() {
  if (seleccionados.size === 0) {
    toast("Selecciona al menos un expediente antes de enviar el correo.", "error");
    return;
  }
  const btn = $("pa-btn-enviar-correo-proveedores");
  btn.disabled = true;
  try {
    const data = await api("/expedientes/enviar-correo-proveedores", {
      method: "POST",
      body: { expedientes: Array.from(seleccionados) },
    });
    toast(`Correo enviado para ${data.enviados} expediente(s).`, "success");
    seleccionados.clear();
    $("pa-chk-todos").checked = false;
    // El envío marca automáticamente esos expedientes como "En Espera de
    // Respuesta" -- se refleja aquí y también en Expedientes (mismo dato de fondo).
    data.expedientes.forEach(exp => notificarCambioEstatus(exp, "En Espera de Respuesta"));
    refrescarVista();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function limpiarFiltros() {
  $("pa-f-expediente").value = "";
  $("pa-f-fechaInicio").value = "";
  $("pa-f-fechaFin").value = "";
  $("pa-f-estatus").value = esPerfilProveedor() ? "En Espera de Respuesta" : "";
  $("pa-f-subservicio").value = "";
  $("pa-f-entidad").value = "";
  msCuentas.limpiar();
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  msCuentas = crearMultiselectCuentas("pa-f-cuentas");

  $("pa-notif-atendidos-cerrar").addEventListener("click", () => $("pa-notif-atendidos").classList.add("hidden"));
  $("pa-f-servicio").addEventListener("change", (e) => cargarSubserviciosEnSelect($("pa-f-subservicio"), e.target.value));
  $("pa-btn-buscar").addEventListener("click", loadExpedientes);
  contenedor.querySelector(".filters-grid").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && !e.target.closest(".ms-panel")) {
      e.preventDefault();
      loadExpedientes();
    }
  });
  $("pa-btn-limpiar").addEventListener("click", () => {
    limpiarFiltros();
    seleccionados.clear();
    loadExpedientes();
  });

  $("pa-chk-todos").addEventListener("change", (e) => {
    const filas = aplicarFiltrosLocales(expedientesActuales);
    filas.forEach(r => {
      if (e.target.checked) seleccionados.add(r.expediente);
      else seleccionados.delete(r.expediente);
    });
    renderTabla(filas);
  });

  $("pa-btn-enviar-correo-proveedores").addEventListener("click", enviarCorreoProveedores);
  $("pa-btn-generar-corte").addEventListener("click", () => abrirModalCorte({
    tipoExpediente: "anticipado",
    seleccionados,
    fuente: expedientesActuales,
    boton: $("pa-btn-generar-corte"),
    alConfirmar: () => {
      seleccionados.clear();
      $("pa-chk-todos").checked = false;
      renderTabla(aplicarFiltrosLocales(expedientesActuales));
    },
  }));

  // Otra pantalla cambió el estatus de un expediente: se actualiza en
  // memoria y se ve reflejado la próxima vez que se entre aquí.
  document.addEventListener(EVENTO_ESTATUS_CAMBIADO, (e) => {
    const rec = expedientesActuales.find(r => r.expediente === e.detail.expediente);
    if (rec) rec.estatus = e.detail.estatus;
  });
}

export function aplicarPermisos() {
  const cabina = esPerfilCabina();
  const proveedor = esPerfilProveedor();
  const admin = esPerfilAdministrador();
  // Mismas reglas de Estado/Entidad/botones que en Expedientes.
  $("pa-f-estatus-field").classList.toggle("hidden-perfil", proveedor);
  $("pa-f-entidad-field").classList.toggle("hidden-perfil", !proveedor);
  $("pa-btn-enviar-correo-proveedores").classList.toggle("hidden-perfil", proveedor || admin);
  $("pa-btn-generar-corte").classList.toggle("hidden-perfil", proveedor || cabina);
  $("pa-kpi-seguimiento-card").classList.toggle("hidden-perfil", !cabina);
  aplicarEtiquetasKPI();
}

export function alEntrar() {
  $("pa-f-expediente").focus();
  if (expedientesActuales.length > 0) {
    // Ya se había buscado antes: solo refresca la vista con lo que ya
    // tenemos en memoria -- no resetea filtros ni vuelve a preguntarle al servidor.
    refrescarVista();
    return;
  }
  // Primera vez que se entra en esta sesión: arranca con los defaults.
  $("pa-f-estatus").value = estatusDefaultParaPerfil();
  $("pa-f-fechaInicio").value = pisoFechaInicioISO();
  $("pa-f-fechaFin").value = hoyISO();
  cargarServiciosFiltro();
  cargarCuentasFiltro();
  loadExpedientes();
}

export function reiniciar() {
  expedientesActuales = [];
  seleccionados.clear();
  paginaActual = 1;
  limpiarFiltros();
  $("pa-f-estatus").value = "";
  $("pa-tabla-body").innerHTML = "";
}
