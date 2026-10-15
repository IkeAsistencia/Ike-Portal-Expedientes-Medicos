/* Alerta flotante en la esquina SUPERIOR derecha, con sonido ligero --
   distinta del toast normal (que va abajo a la derecha, sin sonido).
   Pedida explícitamente para avisar cuando un proveedor responde un
   expediente (ver "Puntos a modificar.docx", sección 1): no bloquea la
   pantalla, no tiene botón de "aceptar", se quita sola a los 10 segundos. */
import { escapeHtml } from "../core/formato.js";

const DURACION_MS = 10000;

let audioCtx = null;

function reproducirSonido() {
  try {
    if (!audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      audioCtx = new Ctx();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    const ahora = audioCtx.currentTime;
    // Dos notas cortas y suaves (tipo "ding" discreto) -- nada estridente,
    // volumen bajo para no fastidiar al usuario.
    [660, 880].forEach((frecuencia, i) => {
      const inicio = ahora + i * 0.12;
      const osc = audioCtx.createOscillator();
      const ganancia = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.value = frecuencia;
      ganancia.gain.setValueAtTime(0, inicio);
      ganancia.gain.linearRampToValueAtTime(0.07, inicio + 0.02);
      ganancia.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.3);
      osc.connect(ganancia).connect(audioCtx.destination);
      osc.start(inicio);
      osc.stop(inicio + 0.32);
    });
  } catch (err) {
    // Si el navegador bloquea audio (por ejemplo, sin interacción previa
    // del usuario en la página), la alerta visual no debe fallar por eso.
    console.warn("No se pudo reproducir el sonido de la alerta:", err.message);
  }
}

/* mensaje: texto a mostrar. silenciosa: true para omitir el sonido (por si
   algún llamador necesita solo el aviso visual). */
export function mostrarAlertaFlotante(mensaje, { silenciosa = false } = {}) {
  const contenedor = document.getElementById("alerta-flotante-container");
  if (!contenedor) return;

  const el = document.createElement("div");
  el.className = "alerta-flotante";
  el.setAttribute("role", "status");
  el.innerHTML = `
    <span class="alerta-flotante-icono">🔔</span>
    <span class="alerta-flotante-texto">${escapeHtml(mensaje)}</span>
  `;
  contenedor.appendChild(el);

  if (!silenciosa) reproducirSonido();

  setTimeout(() => {
    el.classList.add("alerta-flotante-salida");
    setTimeout(() => el.remove(), 300); // deja correr la transición de salida antes de quitarlo del DOM
  }, DURACION_MS);
}
