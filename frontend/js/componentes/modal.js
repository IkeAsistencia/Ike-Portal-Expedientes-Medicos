/* Ventana modal genérica. Se agrega al <body> y se cierra con la "X" o con
   clic fuera de la tarjeta. */

export function crearModal({ id, titulo, cuerpo, pie, ancho, alCerrar }) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay hidden";
  overlay.id = id;
  overlay.innerHTML = `
    <div class="modal-card"${ancho ? ` style="width:${ancho};"` : ""}>
      <div class="modal-header">
        <h3 class="modal-titulo">${titulo}</h3>
        <button class="modal-close" title="Cerrar">&times;</button>
      </div>
      <div class="modal-body">${cuerpo}</div>
      <div class="modal-footer">${pie}</div>
    </div>`;
  document.body.appendChild(overlay);

  const modal = {
    elemento: overlay,
    abrir() { overlay.classList.remove("hidden"); },
    cerrar() {
      overlay.classList.add("hidden");
      if (alCerrar) alCerrar();
    },
    ponerTitulo(texto) { overlay.querySelector(".modal-titulo").textContent = texto; },
  };

  overlay.querySelector(".modal-close").addEventListener("click", () => modal.cerrar());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) modal.cerrar();
  });
  return modal;
}
