/* Alerta PERSISTENTE en la esquina SUPERIOR derecha, con sonido ligero --
   distinta del toast normal (que va abajo a la derecha, sin sonido, y se
   quita solo). Esta no se quita por tiempo: quien llama la actualiza con
   la lista vigente de pendientes (actualizarAlertaPersistente) y la quita
   explícitamente cuando ya no queda nada (quitarAlertaPersistente) --
   pensada para "expedientes con respuesta del proveedor que Cabina
   todavía no resuelve" (ver "Puntos a modificar.docx", sección 1): no
   bloquea la pantalla, no tiene botón de "aceptar". */
let audioCtx = null;

/* Cuántos expedientes se ven sin hacer scroll dentro de la alerta (lo pidió
   el usuario así). De ahí para arriba la lista hace scroll en vez de crecer
   y tapar la pantalla. */
const MAX_FILAS_VISIBLES = 5;

/* Deja la lista a la altura EXACTA de MAX_FILAS_VISIBLES, midiendo dónde
   empieza la fila que sobra.

   Por qué medido y no un max-height fijo en el CSS: ese tope era un número
   en píxeles (155 -> 200 -> 340 -> 170 a lo largo de los rediseños) que
   dependía del alto real del renglón. Al compactar la tabla a 11px las 7
   filas pasaron a medir 154px y cabían dentro del tope de 170px, así que el
   scroll dejó de aparecer: la regla decía "5 filas" pero el CSS permitía 8.
   Midiendo la geometría ya renderizada, el límite sigue siendo 5 aunque
   cambien la tipografía, el interlineado o el número de columnas. */
function limitarAltoDeLista(el, maxFilas = MAX_FILAS_VISIBLES) {
  const lista = el.querySelector(".alerta-flotante-lista");
  // Contraída está en display:none: medir ahí daría 0 (se vuelve a medir al
  // expandirla).
  if (!lista || !lista.offsetParent) return;

  lista.style.maxHeight = "";  // se mide sin tope para saber el alto natural
  const filas = Array.from(lista.querySelectorAll(".alerta-flotante-fila"))
    .filter(f => !f.classList.contains("alerta-flotante-encabezado"));
  if (filas.length <= maxFilas) return;  // caben todas: no hace falta scroll

  // Las filas son display:contents (no tienen caja propia), así que se mide
  // su primera celda.
  const primeraQueSobra = filas[maxFilas]?.firstElementChild;
  if (!primeraQueSobra) return;

  // Si además hay scroll horizontal, su barra se come alto por dentro: se le
  // suma para que las 5 filas se sigan viendo completas.
  const altoBarraHorizontal = lista.offsetHeight - lista.clientHeight;
  const alto = primeraQueSobra.getBoundingClientRect().top - lista.getBoundingClientRect().top;
  lista.style.maxHeight = Math.round(alto + altoBarraHorizontal) + "px";
}

// Posición (desplazamiento horizontal en px) y estado de contraído que el
// usuario le haya dado a cada alerta -- se recuerdan mientras dure la sesión
// (sobreviven a que actualizarAlertaPersistente reconstruya el contenido),
// y se olvidan cuando la alerta se quita del todo (quitarAlertaPersistente).
const posiciones = new Map();
const colapsadas = new Set();

/* Arrastre SOLO horizontal: la alerta vive en la esquina superior derecha
   (posición vertical fija por diseño) y se pidió que únicamente se pueda
   mover hacia los lados, no hacia arriba/abajo. Se mueve con transform
   (no toca left/top), así no interfiere con el layout en columna del
   contenedor de alertas. */
function iniciarArrastre(el, id) {
  let arrastrando = false;
  let inicioX = 0;
  let inicioDesplazamiento = 0;
  let limiteIzq = 0;
  let limiteDer = 0;

  el.addEventListener("pointerdown", (e) => {
    if (e.target.closest("a, button")) return; // no competir con ligas/botones
    arrastrando = true;
    inicioX = e.clientX;
    inicioDesplazamiento = posiciones.get(id) || 0;
    const rect = el.getBoundingClientRect();
    const baseLeft = rect.left - inicioDesplazamiento;
    const margen = 10;
    limiteIzq = margen - baseLeft;
    limiteDer = window.innerWidth - margen - rect.width - baseLeft;
    el.setPointerCapture(e.pointerId);
    el.classList.add("alerta-flotante-arrastrando");
  });
  el.addEventListener("pointermove", (e) => {
    if (!arrastrando) return;
    let desplazamiento = inicioDesplazamiento + (e.clientX - inicioX);
    desplazamiento = Math.min(limiteDer, Math.max(limiteIzq, desplazamiento));
    posiciones.set(id, desplazamiento);
    el.style.transform = `translateX(${desplazamiento}px)`;
  });
  const terminar = (e) => {
    if (!arrastrando) return;
    arrastrando = false;
    el.classList.remove("alerta-flotante-arrastrando");
    try { el.releasePointerCapture(e.pointerId); } catch { /* el pointer ya se soltó */ }
  };
  el.addEventListener("pointerup", terminar);
  el.addEventListener("pointercancel", terminar);
}

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
   cuando se agrega algo nuevo, no en cada refresco).
   colapsable: true agrega un botón para contraer/expandir el contenido --
   pensado como alternativa a mover la alerta, para cuando estorbe algo de
   la pantalla y sea más simple encogerla que arrastrarla.
   expandir: true obliga a que se vea expandida en esta actualización (ej.
   llegó una respuesta nueva) aunque el usuario la hubiera contraído antes --
   para que nunca se le pase una respuesta nueva por tenerla encogida. */
export function actualizarAlertaPersistente(id, mensajeHtml, { tipo = "", sonar = false, colapsable = false, expandir = false, alClicLink } = {}) {
  const contenedor = document.getElementById("alerta-flotante-container");
  if (!contenedor) return;

  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("div");
    el.id = id;
    el.setAttribute("role", "status");
    contenedor.appendChild(el);
    iniciarArrastre(el, id);
    const desplazamiento = posiciones.get(id);
    if (desplazamiento) el.style.transform = `translateX(${desplazamiento}px)`;
  }
  if (expandir) colapsadas.delete(id);
  const colapsada = colapsable && colapsadas.has(id);
  el.className = "alerta-flotante" + (tipo ? ` ${tipo}` : "") + (colapsada ? " alerta-flotante-colapsada" : "");

  const botonColapsar = colapsable
    ? `<button type="button" class="alerta-flotante-colapsar" title="${colapsada ? "Expandir" : "Contraer"}">${colapsada ? "▸" : "▾"}</button>`
    : "";
  el.innerHTML = `
    <span class="alerta-flotante-icono">🔔</span>
    <span class="alerta-flotante-texto">${mensajeHtml}</span>
    ${botonColapsar}
  `;

  // Después de pintar el contenido: el tope de filas visibles se calcula de
  // lo ya renderizado (ver limitarAltoDeLista).
  limitarAltoDeLista(el);

  if (alClicLink) {
    el.querySelectorAll(".alerta-flotante-link").forEach(a => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        alClicLink(parseInt(a.dataset.exp, 10));
      });
    });
  }

  if (colapsable) {
    el.querySelector(".alerta-flotante-colapsar").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const ahoraColapsada = !colapsadas.has(id);
      if (ahoraColapsada) colapsadas.add(id); else colapsadas.delete(id);
      el.classList.toggle("alerta-flotante-colapsada", ahoraColapsada);
      e.currentTarget.textContent = ahoraColapsada ? "▸" : "▾";
      e.currentTarget.title = ahoraColapsada ? "Expandir" : "Contraer";
      // Al expandir hay que volver a medir: mientras estuvo contraída la
      // lista no tenía caja y no se pudo calcular su tope.
      if (!ahoraColapsada) limitarAltoDeLista(el);
    });
  }

  if (sonar) reproducirSonido();
}

/* Quita del todo la alerta con ese id (ej. ya no queda ningún expediente
   pendiente de revisar). No hace nada si no existe -- y olvida su posición
   y si estaba contraída, para que la próxima vez que aparezca (ej. llegó
   una respuesta nueva) arranque limpia. */
export function quitarAlertaPersistente(id) {
  document.getElementById(id)?.remove();
  posiciones.delete(id);
  colapsadas.delete(id);
}
