/* Cierre de sesión por inactividad (30 minutos).

   - Actividad = que la persona use el portal: teclear, hacer clic, mover el
     mouse, desplazarse o tocar la pantalla. Los refrescos automáticos (por
     ejemplo el de Expedientes) NO cuentan: si contaran, la sesión nunca se
     cerraría.
   - Mientras hay actividad, el token se renueva con el servidor (POST
     /auth/renovar, como mucho una vez por minuto). Sin actividad nadie lo
     renueva y vence solo en el servidor: el cierre no depende solo de esta
     pantalla (ver app/core/security.py).
   - Un minuto antes de cerrar aparece un aviso con cuenta regresiva y el
     botón "Seguir conectado". Moverse o teclear con el aviso abierto no lo
     quita: hay que confirmarlo (así no se renueva por un roce del mouse).
   - Si la computadora se suspende, al volver se revisa el tiempo real que
     pasó y, si ya fueron 30 minutos, se cierra al instante. */
import { api } from "./api.js";
import { actualizarToken } from "./sesion.js";
import { crearModal } from "../componentes/modal.js";

const MINUTO = 60 * 1000;
const INACTIVIDAD_MS = 30 * MINUTO;
const AVISO_ANTES_MS = 1 * MINUTO;
const RENOVAR_CADA_MS = 1 * MINUTO;
// Sin "scroll": también lo dispara el portal solo (scrollIntoView al refrescar).
// El desplazamiento real de la persona ya entra por wheel, keydown y touchstart.
const EVENTOS = ["mousedown", "keydown", "wheel", "touchstart", "mousemove"];

let activo = false;
let ultimaActividad = 0;
let ultimaRenovacion = 0;
let renovando = false;
let temporizador = null;
let aviso = null;
let alExpirar = () => {};

function registrarActividad() {
  if (!activo || aviso) return;   // con el aviso abierto solo cuenta "Seguir conectado"
  ultimaActividad = Date.now();
  if (Date.now() - ultimaRenovacion >= RENOVAR_CADA_MS) renovar();
}

async function renovar() {
  if (renovando) return;
  renovando = true;
  ultimaRenovacion = Date.now();
  try {
    const r = await api("/auth/renovar", { method: "POST" });
    if (activo) actualizarToken(r.access_token);
  } catch (err) {
    // Un 401 ya cierra la sesión por su cuenta (core/api.js avisa "sesion-expirada");
    // un error de red se reintenta con la siguiente actividad.
    ultimaRenovacion = 0;
  } finally {
    renovando = false;
  }
}

function revisar() {
  if (!activo) return;
  const inactivo = Date.now() - ultimaActividad;
  if (inactivo >= INACTIVIDAD_MS) {
    terminar();
    alExpirar();
    return;
  }
  const restante = INACTIVIDAD_MS - inactivo;
  if (restante <= AVISO_ANTES_MS) mostrarAviso(restante);
}

function mostrarAviso(restanteMs) {
  const segundos = Math.max(0, Math.ceil(restanteMs / 1000));
  if (!aviso) {
    aviso = crearModal({
      id: "modal-inactividad",
      titulo: "¿Sigues ahí?",
      cuerpo: `<p style="font-size:14px;color:var(--navy);margin:0;">
        Por seguridad, tu sesión se cerrará por inactividad en <b id="inactividad-segundos"></b> segundos.
      </p>`,
      pie: `
        <button class="btn btn-secondary" data-accion="salir">Cerrar sesión</button>
        <button class="btn btn-primary" data-accion="seguir">Seguir conectado</button>`,
      ancho: "420px",
      alCerrar: () => seguirConectado(),   // la "X" o clic fuera también cuentan como "sigo aquí"
    });
    aviso.elemento.querySelector('[data-accion="seguir"]').addEventListener("click", () => seguirConectado());
    aviso.elemento.querySelector('[data-accion="salir"]').addEventListener("click", () => {
      terminar();
      alExpirar({ porUsuario: true });
    });
    aviso.abrir();
    aviso.elemento.querySelector('[data-accion="seguir"]').focus();
  }
  const marcador = aviso.elemento.querySelector("#inactividad-segundos");
  if (marcador) marcador.textContent = String(segundos);
}

function quitarAviso() {
  if (!aviso) return;
  const elemento = aviso.elemento;
  aviso = null;
  elemento.remove();
}

function seguirConectado() {
  if (!activo) return;
  quitarAviso();
  ultimaActividad = Date.now();
  renovar();
}

/* Al entrar al portal (después del login o al recargar con sesión). */
export function iniciarControlDeInactividad({ alExpirar: callback }) {
  detenerControlDeInactividad();
  alExpirar = callback || (() => {});
  activo = true;
  ultimaActividad = Date.now();
  ultimaRenovacion = Date.now();   // el token recién emitido ya trae la ventana completa
  EVENTOS.forEach(ev => window.addEventListener(ev, registrarActividad, { passive: true, capture: true }));
  document.addEventListener("visibilitychange", revisar);
  temporizador = setInterval(revisar, 1000);
}

function terminar() {
  activo = false;
  if (temporizador) clearInterval(temporizador);
  temporizador = null;
  EVENTOS.forEach(ev => window.removeEventListener(ev, registrarActividad, { capture: true }));
  document.removeEventListener("visibilitychange", revisar);
  quitarAviso();
}

/* Al cerrar sesión por cualquier motivo. */
export function detenerControlDeInactividad() {
  terminar();
}

/* Para pruebas: cuánto falta (ms) para el cierre. */
export function msParaCierre() {
  return activo ? Math.max(0, INACTIVIDAD_MS - (Date.now() - ultimaActividad)) : null;
}
