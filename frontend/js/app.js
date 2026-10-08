/* Arranque del portal: monta las pantallas, controla el paso login -> app,
   el menú lateral (según perfil) y la navegación entre pantallas.

   Cada pantalla (js/pantallas/*.js) expone el mismo contrato:
     montar(contenedor)  -> pinta su HTML y conecta sus eventos (una sola vez)
     aplicarPermisos()   -> (opcional) muestra/oculta lo que depende del perfil
     alEntrar()          -> (opcional) cada vez que se navega a ella
     reiniciar()         -> (opcional) al cerrar sesión, limpia su estado
*/
import { getToken, limpiarSesion, nombrePerfilActual, nombreUsuario, esPerfilAdministrador } from "./core/sesion.js";
import { limpiarCatalogos } from "./core/catalogos.js";
import { toast } from "./core/toast.js";
import { iniciarRouter, limpiarRuta, navegar, pantallaEnHash } from "./core/router.js";
import * as login from "./pantallas/login.js";
import * as expedientes from "./pantallas/expedientes.js";
import * as pagoAnticipado from "./pantallas/pago-anticipado.js";
import * as seguimiento from "./pantallas/seguimiento.js";
import * as configuracionCuentas from "./pantallas/configuracion-cuentas.js";
import * as usuariosAccesos from "./pantallas/usuarios-accesos.js";
import * as historialCorreos from "./pantallas/historial-correos.js";
import * as corte from "./pantallas/corte.js";

const PANTALLAS = {
  "expedientes": { modulo: expedientes, titulo: "Expedientes" },
  "pago-anticipado": { modulo: pagoAnticipado, titulo: "Expedientes PA" },
  "seguimiento": { modulo: seguimiento, titulo: "Seguimiento de expedientes", alClicMenu: seguimiento.abrirDesdeMenu },
  "configuracion": { modulo: configuracionCuentas, titulo: "Configuración Cuentas" },
  "accesos": { modulo: usuariosAccesos, titulo: "Usuarios y Accesos" },
  "historial-correos": { modulo: historialCorreos, titulo: "Historial de Correos" },
};

const $ = (id) => document.getElementById(id);

/* ---------- Permisos por perfil ---------- */
function pantallaPermitida(nombre) {
  const admin = esPerfilAdministrador();
  switch (nombre) {
    // Administrador también puede ver Expedientes (para buscar/seleccionar y
    // "Generar corte"), pero sin las acciones operativas de Cabina.
    case "expedientes": return true;
    // "Seguimiento de expedientes" (dar seguimiento al caso) no le corresponde a Administrador.
    case "seguimiento": return !admin;
    // Expedientes PA queda oculta para todos: el flujo de pago anticipado ya
    // vive dentro de Expedientes (casilla "¿Es pago anticipado?" + estatus
    // "Seguimiento de Cita"). El código sigue en pantallas/pago-anticipado.js
    // por si se vuelve a necesitar, pero nadie debe poder llegar a esta pantalla.
    case "pago-anticipado": return false;
    // Configuración Cuentas, Usuarios y Accesos, e Historial de Correos son
    // exclusivos de Administrador.
    case "configuracion":
    case "accesos":
    case "historial-correos": return admin;
    default: return false;
  }
}

function pantallaInicial() {
  // Administrador entra directo a Usuarios y Accesos (su responsabilidad
  // principal); Expedientes queda en el menú para cuando necesite generar un corte.
  return esPerfilAdministrador() ? "accesos" : "expedientes";
}

function aplicarPermisos() {
  document.querySelectorAll(".nav-item[data-pantalla]").forEach(item => {
    item.classList.toggle("hidden-perfil", !pantallaPermitida(item.dataset.pantalla));
  });
  Object.values(PANTALLAS).forEach(({ modulo }) => modulo.aplicarPermisos?.());
}

/* ---------- Navegación ---------- */
function mostrarPantalla(nombre) {
  if (!getToken()) return;
  if (!PANTALLAS[nombre] || !pantallaPermitida(nombre)) {
    navegar(pantallaInicial());
    return;
  }
  Object.keys(PANTALLAS).forEach((key) => {
    $("screen-" + key).classList.toggle("active", key === nombre);
  });
  document.querySelectorAll(".nav-item[data-pantalla]").forEach(item => {
    item.classList.toggle("active", item.dataset.pantalla === nombre);
  });
  const { modulo, titulo } = PANTALLAS[nombre];
  $("topbar-title").textContent = titulo;
  $("topbar-crumbs").innerHTML = "Inicio &nbsp;›&nbsp; <b>" + titulo + "</b>";
  modulo.alEntrar?.();
}

/* ---------- Sesión ---------- */
function mostrarApp() {
  $("view-login").classList.add("hidden");
  $("view-app").classList.remove("hidden");
  const perfil = nombrePerfilActual();
  $("nav-user").textContent = "Sesión: " + nombreUsuario() + (perfil ? " (" + perfil + ")" : "");
  aplicarPermisos();
  expedientes.iniciarPolling();
  // Si se recargó la página estando en una pantalla, se queda en esa.
  navegar(pantallaEnHash() || pantallaInicial());
}

function cerrarSesion(silencioso) {
  limpiarSesion();
  limpiarCatalogos();
  corte.reiniciar();
  Object.values(PANTALLAS).forEach(({ modulo }) => modulo.reiniciar?.());
  limpiarRuta();
  $("view-app").classList.add("hidden");
  $("view-login").classList.remove("hidden");
  login.mostrarPasoRfc();
  if (!silencioso) toast("Sesión cerrada");
}

/* ---------- Arranque ---------- */
function montarPantallas() {
  const contenido = $("contenido");
  Object.entries(PANTALLAS).forEach(([nombre, { modulo }]) => {
    const div = document.createElement("div");
    div.className = "screen";
    div.id = "screen-" + nombre;
    contenido.appendChild(div);
    modulo.montar(div);
  });

  document.querySelectorAll(".nav-item[data-pantalla]").forEach(item => {
    const { alClicMenu } = PANTALLAS[item.dataset.pantalla];
    item.addEventListener("click", () => (alClicMenu ? alClicMenu() : navegar(item.dataset.pantalla)));
  });
  $("nav-salir").addEventListener("click", () => cerrarSesion(false));
}

login.montar($("view-login"), { alEntrar: mostrarApp });
montarPantallas();
iniciarRouter(mostrarPantalla);

window.addEventListener("sesion-expirada", () => {
  cerrarSesion(true);
  toast("Tu sesión expiró, inicia sesión de nuevo.", "error");
});

// Si ya había una sesión activa en este mismo tab (recarga de página), no pedir login de nuevo.
if (getToken()) {
  mostrarApp();
} else {
  $("view-login").classList.remove("hidden");
  login.iniciar();
}
