/* Sesión del usuario (token y datos del login) y helpers de perfil. */

export const PERFIL_ADMINISTRADOR = 1;
export const PERFIL_CABINA = 2;
export const PERFIL_PROVEEDOR = 3;
export const NOMBRES_PERFIL = { "1": "Administrador", "2": "Cabina", "3": "Proveedor" };

export function getToken() { return sessionStorage.getItem("token"); }

export function guardarSesion(data, rfc) {
  sessionStorage.setItem("token", data.access_token);
  sessionStorage.setItem("rfc", data.rfc);
  sessionStorage.setItem("nombre", data.nombre);
  sessionStorage.setItem("perfil", data.perfil);
  localStorage.setItem("ultimoRfc", rfc);
}

export function limpiarSesion() {
  sessionStorage.removeItem("token");
  sessionStorage.removeItem("rfc");
  sessionStorage.removeItem("nombre");
  sessionStorage.removeItem("perfil");
}

export function nombreUsuario() { return sessionStorage.getItem("nombre"); }
export function ultimoRfc() { return localStorage.getItem("ultimoRfc"); }

export function perfilActual() {
  return parseInt(sessionStorage.getItem("perfil"), 10) || null;
}
export function nombrePerfilActual() {
  return NOMBRES_PERFIL[String(perfilActual())] || "";
}
export function esPerfilCabina() { return perfilActual() === PERFIL_CABINA; }
export function esPerfilProveedor() { return perfilActual() === PERFIL_PROVEEDOR; }
export function esPerfilAdministrador() { return perfilActual() === PERFIL_ADMINISTRADOR; }
