/* Diálogo con el estilo del portal que pide un texto obligatorio (por ejemplo,
   el motivo de una cancelación) antes de confirmar. Devuelve una promesa: el
   texto escrito si confirman, o null si cancelan, cierran con la "X", hacen
   clic fuera o presionan Esc. El botón de confirmar se habilita hasta que el
   texto tiene el mínimo de caracteres. */
import { crearModal } from "./modal.js";

const escapar = (texto) =>
  String(texto).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function pedirMotivo({
  titulo, mensaje, etiqueta = "Motivo", placeholder = "", minimo = 10, maximo = 500,
  textoConfirmar = "Aceptar", textoCancelar = "Cancelar", peligro = false,
}) {
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
      id: "modal-pedir-motivo",
      titulo: escapar(titulo),
      cuerpo: `
        <p style="font-size:14px;color:var(--navy);margin:0 0 12px;">${escapar(mensaje)}</p>
        <div class="field">
          <label for="pm-motivo">${escapar(etiqueta)}</label>
          <textarea id="pm-motivo" rows="4" maxlength="${maximo}" placeholder="${escapar(placeholder)}"></textarea>
          <div class="hint" id="pm-contador"></div>
        </div>`,
      pie: `
        <button class="btn btn-secondary" data-accion="cancelar">${escapar(textoCancelar)}</button>
        <button class="btn ${peligro ? "btn-danger" : "btn-primary"}" data-accion="confirmar" disabled>${escapar(textoConfirmar)}</button>`,
      ancho: "480px",
      alCerrar: () => terminar(null),
    });
    const campo = modal.elemento.querySelector("#pm-motivo");
    const contador = modal.elemento.querySelector("#pm-contador");
    const boton = modal.elemento.querySelector('[data-accion="confirmar"]');
    const limpio = () => campo.value.trim().replace(/\s+/g, " ");
    const actualizar = () => {
      const largo = limpio().length;
      boton.disabled = largo < minimo;
      contador.textContent = largo < minimo
        ? `Escribe al menos ${minimo} caracteres (llevas ${largo}).`
        : `${campo.value.length} / ${maximo}`;
    };
    campo.addEventListener("input", actualizar);
    modal.elemento.querySelector('[data-accion="cancelar"]').addEventListener("click", () => modal.cerrar());
    boton.addEventListener("click", () => {
      if (boton.disabled) return;
      terminar(limpio());
      modal.elemento.classList.add("hidden");
    });
    document.addEventListener("keydown", alTeclear);
    actualizar();
    modal.abrir();
    campo.focus();
  });
}
