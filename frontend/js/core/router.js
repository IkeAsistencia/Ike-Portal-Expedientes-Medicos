/* Navegación entre pantallas por hash (#/expedientes, #/seguimiento, ...):
   el botón "atrás" del navegador funciona y al recargar se queda en la
   misma pantalla. Qué hacer al cambiar de pantalla lo decide app.js. */

let manejador = () => {};

export function iniciarRouter(alCambiar) {
  manejador = alCambiar;
  window.addEventListener("hashchange", () => manejador(pantallaEnHash()));
}

export function pantallaEnHash() {
  return location.hash.replace(/^#\/?/, "") || null;
}

export function navegar(pantalla) {
  const destino = "#/" + pantalla;
  // Si ya estamos ahí, el navegador no dispara "hashchange": se llama directo
  // para que la pantalla se refresque igual que al entrar.
  if (location.hash === destino) manejador(pantalla);
  else location.hash = destino;
}

export function limpiarRuta() {
  history.replaceState(null, "", location.pathname + location.search);
}
