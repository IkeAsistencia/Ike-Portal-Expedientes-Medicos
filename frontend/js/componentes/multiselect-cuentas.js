/* Dropdown "Cuenta (una o varias)" con buscador, "Seleccionar todo" y
   "Limpiar". Usa el catálogo compartido de cuentas (core/catalogos.js).

   Uso:
     plantilla:  multiselectCuentasHtml("f-cuentas")
     después de insertarla en el DOM:  const ms = crearMultiselectCuentas("f-cuentas");
*/
import { catalogoCuentas } from "../core/catalogos.js";
import { escapeHtml } from "../core/formato.js";
import { ICONOS } from "./iconos.js";

export function multiselectCuentasHtml(idBase) {
  return `
    <div class="ms-dropdown" id="${idBase}-dropdown">
      <button type="button" class="ms-toggle" id="${idBase}-toggle">
        <span id="${idBase}-toggle-text">Todas las cuentas</span>
        ${ICONOS.chevron}
      </button>
      <div class="ms-panel hidden" id="${idBase}-panel">
        <div class="ms-search"><input type="text" id="${idBase}-search" placeholder="Buscar cuenta..." autocomplete="off"></div>
        <div class="ms-actions">
          <button type="button" class="ms-link" id="${idBase}-selectall">Seleccionar todo</button>
          <button type="button" class="ms-link" id="${idBase}-clear">Limpiar</button>
        </div>
        <div class="ms-options" id="${idBase}-options"></div>
      </div>
    </div>`;
}

export function crearMultiselectCuentas(idBase) {
  const seleccionadas = new Set();
  const dropdown = document.getElementById(`${idBase}-dropdown`);
  const toggleBtn = document.getElementById(`${idBase}-toggle`);
  const panel = document.getElementById(`${idBase}-panel`);
  const opciones = document.getElementById(`${idBase}-options`);
  const textoToggle = document.getElementById(`${idBase}-toggle-text`);

  function renderOpciones(lista) {
    if (!lista.length) {
      opciones.innerHTML = `<div class="ms-empty">Sin resultados.</div>`;
      return;
    }
    opciones.innerHTML = lista.map(c => `
      <label class="ms-option">
        <input type="checkbox" value="${escapeHtml(String(c.clave))}" ${seleccionadas.has(String(c.clave)) ? "checked" : ""}>
        <span>${escapeHtml(c.descripcion)}</span>
      </label>
    `).join("");
    opciones.querySelectorAll('input[type="checkbox"]').forEach(chk => {
      chk.addEventListener("change", (e) => {
        if (e.target.checked) seleccionadas.add(e.target.value);
        else seleccionadas.delete(e.target.value);
        actualizarTexto();
      });
    });
  }

  function actualizarTexto() {
    const n = seleccionadas.size;
    if (n === 0) {
      textoToggle.textContent = "Todas las cuentas";
    } else if (n === 1) {
      const clave = Array.from(seleccionadas)[0];
      const c = catalogoCuentas().find(x => String(x.clave) === clave);
      textoToggle.textContent = c ? c.descripcion : "1 cuenta seleccionada";
    } else {
      textoToggle.textContent = `${n} cuentas seleccionadas`;
    }
  }

  function renderizar() {
    renderOpciones(catalogoCuentas());
    actualizarTexto();
  }

  toggleBtn.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    toggleBtn.classList.toggle("open", !panel.classList.contains("hidden"));
  });
  document.getElementById(`${idBase}-search`).addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    renderOpciones(catalogoCuentas().filter(c => c.descripcion.toLowerCase().includes(q)));
  });
  document.getElementById(`${idBase}-selectall`).addEventListener("click", () => {
    catalogoCuentas().forEach(c => seleccionadas.add(String(c.clave)));
    renderizar();
  });
  document.getElementById(`${idBase}-clear`).addEventListener("click", () => {
    seleccionadas.clear();
    renderizar();
  });
  // Clic fuera del dropdown: se cierra.
  document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target)) {
      panel.classList.add("hidden");
      toggleBtn.classList.remove("open");
    }
  });

  return {
    seleccionadas: () => Array.from(seleccionadas),
    renderizar,
    limpiar() {
      seleccionadas.clear();
      renderizar();
    },
  };
}
