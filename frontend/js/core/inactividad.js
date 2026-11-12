/* Cierre de sesión por inactividad (30 minutos).

   - Actividad = que la persona use el portal: teclear, hacer clic, mover el
     mouse, desplazarse o tocar la pantalla. Los refrescos automáticos (por
     ejemplo el de Expedientes) NO cuentan: si contaran, la sesión nunca se
     cerraría.
   - Mientras hay actividad, el token se renueva con el servidor (POST
     /auth/renovar, como mucho una vez cada 15 minutos). Sin actividad nadie
     lo renueva y vence solo en el servidor: el cierre no depende solo de esta
     pantalla (ver app/core/security.py, que da al token 30 + 15 + 2 minutos).
   - Si una renovación falla (red caída, bloqueo del WAF de AWS), NO se
     reintenta con cada movimiento del mouse: se espera 1, 2, 4 y luego cada
     5 minutos. Antes se reintentaba al instante y eso generaba ráfagas de
     cientos de peticiones que hacían que AWS bloqueara la IP de la oficina.
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
const RENOVAR_CADA_MS = 15 * MINUTO;            // ver RENOVAR_CADA_MINUTOS en app/core/security.py
const ESPERAS_TRAS_FALLA_MS = [1, 2, 4, 5].map(m => m * MINUTO);   // la última se repite
// Sin "scroll": también lo dispara el portal solo (scrollIntoView al refrescar).
// El desplazamiento real de la persona ya entra por wheel, keydown y touchstart.
const EVENTOS = ["mousedown", "keydown", "wheel", "touchstart", "mousemove"];

let activo = false;
let ultimaActividad = 0;
let ultimaRenovacion = 0;
let renovando = false;
let fallasSeguidas = 0;
let siguienteIntentoTrasFalla = 0;
let temporizador = null;
let aviso = null;
let alExpirar = () => {};

function registrarActividad() {
  if (!activo || aviso) return;   // con el aviso abierto solo cuenta "Seguir conectado"
  ultimaActividad = Date.now();
  if (tocaRenovar()) renovar();
}

function tocaRenovar() {
  const ahora = Date.now();
  if (fallasSeguidas > 0) return ahora >= siguienteIntentoTrasFalla;
  return ahora - ultimaRenovacion >= RENOVAR_CADA_MS;
}

async function renovar() {
  if (renovando) return;
  renovando = true;
  try {
    const r = await api("/auth/renovar", { method: "POST" });
    if (activo) actualizarToken(r.access_token);
    ultimaRenovacion = Date.now();
    fallasSeguidas = 0;
  } catch (err) {
    // Un 401 ya cierra la sesión por su cuenta (core/api.js avisa "sesion-expirada").
    // Cualquier otro error se reintenta con la siguiente actividad, pero
    // hasta que pase la espera: el token todavía aguanta de sobra.
    fallasSeguidas += 1;
    const espera = ESPERAS_TRAS_FALLA_MS[Math.min(fallasSeguidas, ESPERAS_TRAS_FALLA_MS.length) - 1];
    siguienteIntentoTrasFalla = Date.now() + espera;
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
  fallasSeguidas = 0;
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
