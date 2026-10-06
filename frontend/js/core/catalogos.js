/* Catálogos compartidos entre pantallas (cuentas, servicios, subservicios,
   entidades). Cuentas y entidades se guardan en memoria para no pedirlos de
   nuevo en cada pantalla; se limpian al cerrar sesión. */
import { api } from "./api.js";
import { escapeHtml } from "./formato.js";
import { toast } from "./toast.js";

let cuentas = [];
let entidades = [];

export function limpiarCatalogos() {
  cuentas = [];
  entidades = [];
}

/* ---------- Cuentas ---------- */
export function catalogoCuentas() { return cuentas; }

export async function cargarCatalogoCuentas({ forzar = false } = {}) {
  if (cuentas.length && !forzar) return cuentas;
  try {
    cuentas = await api("/catalogos/cuentas");
  } catch (err) {
    toast("No se pudo cargar el catálogo de cuentas: " + err.message, "error");
  }
  return cuentas;
}

/* ---------- Servicios / subservicios (llenan un <select>) ---------- */
export async function cargarServiciosEnSelect(select) {
  try {
    const servicios = await api("/catalogos/servicios");
    select.innerHTML = servicios.map(s => `<option value="${s.clave}">${escapeHtml(s.descripcion)}</option>`).join("");
    return servicios;
  } catch (err) {
    toast("No se pudo cargar el catálogo de servicios: " + err.message, "error");
    return [];
  }
}

export async function cargarSubserviciosEnSelect(select, clServicio) {
  select.innerHTML = `<option value="">Todos</option>`;
  if (!clServicio) return null;
  try {
    const subservicios = await api("/catalogos/subservicios", { params: { cl_servicio: clServicio } });
    select.innerHTML += subservicios.map(s => `<option value="${s.clave}">${escapeHtml(s.descripcion)}</option>`).join("");
    return subservicios;
  } catch (err) {
    toast("No se pudo cargar el catálogo de subservicios: " + err.message, "error");
    return null;
  }
}

/* ---------- Entidades ---------- */
// Catálogo fijo de las 32 entidades -- se comparte entre el alta de
// Proveedor (admin) y los filtros de Entidad de Expedientes/Expedientes PA.
export async function cargarCatalogoEntidades() {
  if (entidades.length) return entidades;
  try {
    entidades = await api("/admin/accesos/entidades");
  } catch (err) {
    toast("No se pudo cargar el catálogo de entidades: " + err.message, "error");
  }
  return entidades;
}

export function poblarSelectEntidades(select, opcionVacia) {
  const seleccionActual = select.value;
  select.innerHTML = `<option value="">${opcionVacia}</option>` +
    entidades.map(e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`).join("");
  if (entidades.includes(seleccionActual)) select.value = seleccionActual;
}
