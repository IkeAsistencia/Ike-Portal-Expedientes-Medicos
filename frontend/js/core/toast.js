/* Avisos flotantes (esquina inferior derecha). */

export function toast(message, type, duracionMs) {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = "toast" + (type ? " " + type : "");
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), duracionMs || 4000);
}
