/* Alerta PERSISTENTE en la esquina SUPERIOR derecha, con sonido ligero --
   distinta del toast normal (que va abajo a la derecha, sin sonido, y se
   quita solo). Esta no se quita por tiempo: quien llama la actualiza con
   la lista vigente de pendientes (actualizarAlertaPersistente) y la quita
   explícitamente cuando ya no queda nada (quitarAlertaPersistente) --
   pensada para "expedientes con respuesta del proveedor que Cabina
   todavía no resuelve" (ver "Puntos a modificar.docx", sección 1): no
   bloquea la pantalla, no tiene botón de "aceptar". */
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

/* id: identifica la alerta -- si ya existe una con ese id, se actualiza su
   contenido en el mismo lugar (sin re-animar la entrada ni duplicar el
   recuadro); si no existe, se crea.
   mensajeHtml: HTML ya armado por quien llama (el texto suelto debe venir
   escapado -- ver escapeHtml en core/formato.js; los números de expediente
   son seguros de interpolar tal cual). Puede incluir enlaces con
   class="alerta-flotante-link" y data-exp="<número>", iguales a los de la
   columna Expediente de la tabla -- alClicLink(expediente) se llama al
   darle clic a cualquiera de ellos.
   tipo: clase extra en el contenedor, para variar el color según el
   motivo de la alerta (ej. "proveedor-respondio" = naranja).
   sonar: true para reproducir el sonido en esta actualización (solo
   cuando se agrega algo nuevo, no en cada refresco). */
export function actualizarAlertaPersistente(id, mensajeHtml, { tipo = "", sonar = false, alClicLink } = {}) {
  const contenedor = document.getElementById("alerta-flotante-container");
  if (!contenedor) return;

  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("div");
    el.id = id;
    el.setAttribute("role", "status");
    contenedor.appendChild(el);
  }
  el.className = "alerta-flotante" + (tipo ? ` ${tipo}` : "");
  el.innerHTML = `
    <span class="alerta-flotante-icono">🔔</span>
    <span class="alerta-flotante-texto">${mensajeHtml}</span>
  `;

  if (alClicLink) {
    el.querySelectorAll(".alerta-flotante-link").forEach(a => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        alClicLink(parseInt(a.dataset.exp, 10));
      });
    });
  }

  if (sonar) reproducirSonido();
}

/* Quita del todo la alerta con ese id (ej. ya no queda ningún expediente
   pendiente de revisar). No hace nada si no existe. */
export function quitarAlertaPersistente(id) {
  document.getElementById(id)?.remove();
}
