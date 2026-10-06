/* Pantalla: Configuración Cuentas (solo Administrador). */
import { api } from "../core/api.js";
import { escapeHtml } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { ICONOS } from "../componentes/iconos.js";

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2>Agregar cuenta</h2></div>
    <div class="card-body">
      <div class="field autocomplete">
        <label for="cfg-buscar-cuenta">Cuenta (escribe al menos 3 letras)</label>
        <input type="text" id="cfg-buscar-cuenta" placeholder="Nombre de la cuenta" autocomplete="off">
        <div class="suggestions hidden" id="cfg-suggestions"></div>
      </div>
    </div>
  </div>

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Cuentas configuradas (<span id="cfgCount">0</span>)</h2>
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead><tr><th style="width:40px;">#</th><th>Cuenta</th><th style="width:80px;">Acciones</th></tr></thead>
        <tbody id="cfg-tbody"></tbody>
      </table>
    </div>
    <div class="card-body" style="border-top:1px solid var(--gray-border);">
      <div class="actions-row between">
        <button class="btn btn-secondary" id="cfg-cancelar-btn">Cancelar</button>
        <button class="btn btn-primary" id="cfg-aceptar-btn">Aceptar</button>
      </div>
    </div>
  </div>`;

let debounceTimer = null;

const $ = (id) => document.getElementById(id);

function buscarSugerencias(e) {
  clearTimeout(debounceTimer);
  const texto = e.target.value.trim();
  const suggestionsEl = $("cfg-suggestions");

  const soloAlfabetico = /^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]*$/.test(texto);
  if (texto.length < 3 || !soloAlfabetico) {
    suggestionsEl.classList.add("hidden");
    suggestionsEl.innerHTML = "";
    return;
  }

  debounceTimer = setTimeout(async () => {
    try {
      const resultados = await api("/catalogos/cuentas/buscar", { params: { texto } });
      if (!resultados.length) {
        suggestionsEl.innerHTML = `<div class="empty-suggestion">Sin resultados.</div>`;
      } else {
        suggestionsEl.innerHTML = resultados.map(c =>
          `<div data-cl="${c.cl_cuenta}" data-nombre="${escapeHtml(c.nombre)}">${c.cl_cuenta} — ${escapeHtml(c.nombre)}</div>`
        ).join("");
        suggestionsEl.querySelectorAll("div[data-cl]").forEach(div => {
          div.addEventListener("click", () => agregarCuenta(div.dataset.cl, div.dataset.nombre));
        });
      }
      suggestionsEl.classList.remove("hidden");
    } catch (err) {
      toast(err.message, "error");
    }
  }, 300);
}

async function agregarCuenta(clCuenta, nombre) {
  try {
    await api("/configuracion/cuentas", { method: "POST", body: { cl_cuenta: parseInt(clCuenta, 10), nombre } });
    $("cfg-buscar-cuenta").value = "";
    $("cfg-suggestions").classList.add("hidden");
    toast("Cuenta agregada.", "success");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function cargarGrid() {
  const tbody = $("cfg-tbody");
  tbody.innerHTML = `<tr><td colspan="3" class="mini-empty">Cargando…</td></tr>`;
  try {
    const cuentas = await api("/configuracion/cuentas");
    $("cfgCount").textContent = cuentas.length;
    if (!cuentas.length) {
      tbody.innerHTML = `<tr><td colspan="3" class="mini-empty">Aún no hay cuentas configuradas.</td></tr>`;
      return;
    }
    tbody.innerHTML = cuentas.map((c, i) => `
      <tr>
        <td data-label="#">${i + 1}</td>
        <td data-label="Cuenta"><span class="cuenta-chip">${escapeHtml(String(c.cl_cuenta))}</span>${escapeHtml(c.nombre)}</td>
        <td data-label="Acciones">
          <button class="icon-btn" data-cl="${c.cl_cuenta}" title="Eliminar cuenta">${ICONOS.basura}</button>
        </td>
      </tr>
    `).join("");
    tbody.querySelectorAll(".icon-btn").forEach(btn => {
      btn.addEventListener("click", () => eliminarCuenta(btn.dataset.cl));
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="3" class="mini-empty">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function eliminarCuenta(clCuenta) {
  try {
    await api("/configuracion/cuentas/" + clCuenta, { method: "DELETE" });
    toast("Cuenta eliminada.");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function limpiarGrid() {
  try {
    await api("/configuracion/cuentas/limpiar", { method: "POST" });
    toast("Grid limpiado.");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  $("cfg-buscar-cuenta").addEventListener("input", buscarSugerencias);
  $("cfg-cancelar-btn").addEventListener("click", limpiarGrid);
  $("cfg-aceptar-btn").addEventListener("click", () => {
    // Cada cuenta ya se guardó al agregarla; este botón es solo confirmación visual.
    toast("Configuración guardada.", "success");
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#screen-configuracion .autocomplete")) {
      $("cfg-suggestions").classList.add("hidden");
    }
  });
}

export function alEntrar() {
  cargarGrid();
  $("cfg-buscar-cuenta").focus();
}
