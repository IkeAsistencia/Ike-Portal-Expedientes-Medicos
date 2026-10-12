/* Aviso de confirmación con el estilo del portal (reemplaza al confirm() del
   navegador). Devuelve una promesa: true si confirman, false si cancelan,
   cierran con la "X", hacen clic fuera o presionan Esc. */
import { crearModal } from "./modal.js";

const escapar = (texto) =>
  String(texto).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function confirmar({ titulo, mensaje, textoConfirmar = "Aceptar", textoCancelar = "Cancelar", peligro = false }) {
  return new Promise((resolve) => {
    let resuelto = false;
    const terminar = (valor) => {
      if (resuelto) return;
      resuelto = true;
      document.removeEventListener("keydown", alTeclear);
      resolve(valor);
      setTimeout(() => modal.elemento.remove(), 0);
    };
    const alTeclear = (e) => { if (e.key === "Escape") modal.cerrar(); };

    const modal = crearModal({
      id: "modal-confirmar",
      titulo: escapar(titulo),
      cuerpo: `<p style="font-size:14px;color:var(--navy);margin:0;">${escapar(mensaje)}</p>`,
      pie: `
        <button class="btn btn-secondary" data-accion="cancelar">${escapar(textoCancelar)}</button>
        <button class="btn ${peligro ? "btn-danger" : "btn-primary"}" data-accion="confirmar">${escapar(textoConfirmar)}</button>`,
      ancho: "440px",
      alCerrar: () => terminar(false),
    });
    modal.elemento.querySelector('[data-accion="cancelar"]').addEventListener("click", () => modal.cerrar());
    modal.elemento.querySelector('[data-accion="confirmar"]').addEventListener("click", () => {
      terminar(true);
      modal.elemento.classList.add("hidden");
    });
    document.addEventListener("keydown", alTeclear);
    modal.abrir();
    modal.elemento.querySelector('[data-accion="confirmar"]').focus();
  });
}
