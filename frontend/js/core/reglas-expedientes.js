/* Reglas de negocio de expedientes que comparten varias pantallas:
   estatus por perfil, rango de fechas y el filtro temporal de subservicios. */
import { esPerfilCabina, esPerfilProveedor } from "./sesion.js";

// Estados a los que Cabina "regresa" el expediente a Proveedor -- ambos
// exigen comentario obligatorio (ver sg-motivo-regreso-field).
export const ESTATUS_DE_REGRESO = ["En Espera de Respuesta", "Seguimiento de Cita"];

// Proveedor solo puede ver expedientes en estos estatus: "En Espera de
// Respuesta" y "Seguimiento de Cita" (los que le corresponde atender) y
// "Seguimiento Proveedor" (los que ya mandó, en modo solo lectura mientras
// Cabina los revisa). Cualquier otro estatus (Abierto, Finalizado) no le
// corresponde verlo.
export const ESTATUS_VISIBLES_PROVEEDOR = ["En Espera de Respuesta", "Seguimiento Proveedor", "Seguimiento de Cita"];
// De esos, en cuáles puede realmente registrar/actualizar algo (en
// "Seguimiento Proveedor" solo puede ver, ya está en revisión de Cabina).
export const ESTATUS_ACCIONABLES_PROVEEDOR = ["En Espera de Respuesta", "Seguimiento de Cita"];

export function proveedorPuedeVer(estatus) {
  return !esPerfilProveedor() || ESTATUS_VISIBLES_PROVEEDOR.includes(estatus);
}

export function estatusDefaultParaPerfil() {
  // Cabina arranca en "Abierto" (su bandeja de trabajo). Proveedor y
  // Administrador arrancan en "En Espera de Respuesta" -- para Proveedor es
  // lo único que le corresponde ver; para Administrador es lo más útil para
  // generar el corte (evidencia de qué se mandó a proveedor).
  if (esPerfilCabina()) return "Abierto";
  return "En Espera de Respuesta";
}

/* Cuando una pantalla cambia el estatus de un expediente (Seguimiento,
   envío de correo), avisa con este evento para que las demás pantallas
   actualicen lo que ya tienen en memoria sin volver a pedirlo al servidor. */
export const EVENTO_ESTATUS_CAMBIADO = "expediente:estatus-cambiado";

export function notificarCambioEstatus(expediente, estatus) {
  document.dispatchEvent(new CustomEvent(EVENTO_ESTATUS_CAMBIADO, { detail: { expediente, estatus } }));
}

/* ---------- Rango de fechas ---------- */
export const MESES_MAXIMOS_RANGO = 3;

export function pisoFechaInicioISO() {
  const piso = new Date();
  piso.setMonth(piso.getMonth() - MESES_MAXIMOS_RANGO);
  return piso.toISOString().slice(0, 10);
}

export function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

export function validarRangoFechas(fechaInicioStr, fechaFinStr) {
  // Ojo: esto NO prohíbe buscar fechas viejas (ej. dentro de 2025) -- solo
  // limita qué tan ancho puede ser el rango entre inicio y fin. Pero si se
  // manda una de las dos fechas, se deben mandar AMBAS -- si no, la regla
  // de los 3 meses se podría brincar por completo (ej. solo fecha inicio
  // desde 2022, sin tope superior).
  if (fechaInicioStr && !fechaFinStr) return "Debes indicar también la fecha fin para poder buscar.";
  if (fechaFinStr && !fechaInicioStr) return "Debes indicar también la fecha inicio para poder buscar.";
  if (!fechaInicioStr || !fechaFinStr) return null;
  const inicio = new Date(fechaInicioStr + "T00:00:00");
  const fin = new Date(fechaFinStr + "T00:00:00");
  if (fin < inicio) return "La fecha fin no puede ser anterior a la fecha inicio.";
  const limite = new Date(inicio);
  limite.setMonth(limite.getMonth() + MESES_MAXIMOS_RANGO);
  if (fin > limite) {
    return `El rango de fechas no puede ser mayor a ${MESES_MAXIMOS_RANGO} meses.`;
  }
  return null;
}

/* ---------- Filtro temporal de subservicios ---------- */
// TEMPORAL: solo se trabaja con los subservicios del catálogo (acordado con
// el equipo). null = catálogo aún no cargado (no filtrar todavía).
let subserviciosPermitidos = null;

export function establecerSubserviciosPermitidos(subservicios) {
  subserviciosPermitidos = subservicios.map(s => s.descripcion.trim().toLowerCase());
}

export function aplicarFiltroSubservicioLocal(rows) {
  if (!subserviciosPermitidos) return rows;
  return rows.filter(r => subserviciosPermitidos.includes((r.tipo_subservicio || "").trim().toLowerCase()));
}
