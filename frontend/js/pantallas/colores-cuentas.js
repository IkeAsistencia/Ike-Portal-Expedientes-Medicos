/* Pantalla: Colores de Cuentas (solo Administrador).
   Se elige una cuenta que ya existe en el sistema central y se le pone un prefijo corto y
   un color (paleta pastel fija). A partir de ahí, Expedientes pinta el
   renglón de ese color y muestra el prefijo junto a la cuenta (lo ven todos
   los perfiles). Se puede cambiar o quitar en cualquier momento.
   Es independiente de Configuración Cuentas. */
import { api } from "../core/api.js";
import { escapeHtml, formatDateTime } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { confirmar } from "../componentes/confirmar.js";

const LARGO_MAXIMO_PREFIJO = 12;

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2 id="cc-titulo-form">Etiquetar una cuenta</h2></div>
    <div class="card-body">
      <div class="field autocomplete" id="cc-campo-buscar">
        <label for="cc-buscar">Cuenta (escribe al menos 3 letras)</label>
        <input type="text" id="cc-buscar" placeholder="Nombre de la cuenta" autocomplete="off">
        <div class="suggestions hidden" id="cc-sugerencias"></div>
      </div>
      <div class="cc-seleccionada hidden" id="cc-seleccionada">
        <span class="muted">Cuenta elegida:</span>
        <strong id="cc-seleccionada-nombre"></strong>
        <button type="button" class="btn-link-semaforo" id="cc-cambiar">Cambiar</button>
      </div>

      <div class="cc-fila">
        <div class="field cc-prefijo">
          <label for="cc-prefijo">Prefijo (opcional)</label>
          <input type="text" id="cc-prefijo" maxlength="${LARGO_MAXIMO_PREFIJO}" placeholder="Ej. QUA" autocomplete="off">
          <div class="hint">Hasta ${LARGO_MAXIMO_PREFIJO} caracteres. Se muestra junto a la cuenta en Expedientes.</div>
        </div>
        <div class="field">
          <label>Color</label>
          <div class="cc-paleta" id="cc-paleta"></div>
        </div>
      </div>

      <div class="cc-vista-previa">
        <span class="muted">Así se verá en Expedientes:</span>
        <div id="cc-vista-previa" class="cc-muestra"></div>
      </div>

      <div class="actions-row">
        <button class="btn btn-secondary hidden" id="cc-cancelar-edicion">Cancelar edición</button>
        <button class="btn btn-primary" id="cc-guardar">Guardar</button>
      </div>
    </div>
  </div>

  <div class="card tono-verdeazul">
    <div class="card-header"><h2>Cuentas con color (<span id="cc-contador">0</span>)</h2></div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr>
            <th style="width:40px;">#</th><th>Cuenta</th><th style="width:160px;">Etiqueta</th>
            <th style="width:100px;">Color</th><th style="width:210px;">Última modificación</th><th style="width:170px;">Acciones</th>
          </tr>
        </thead>
        <tbody id="cc-tbody"></tbody>
      </table>
    </div>
  </div>`;

const $ = (id) => document.getElementById(id);

let paleta = [];          // [{clave, nombre}] que manda el servidor
let etiquetas = [];       // cuentas con color
let seleccion = null;     // { cl_cuenta, nombre } de la cuenta que se está etiquetando
let colorElegido = null;
let debounce = null;

const nombreColor = (clave) => (paleta.find(c => c.clave === clave) || {}).nombre || clave;
// La clave viene del servidor, pero se limita a letras por si acaso (va a una clase CSS).
const claseColor = (clave) => "cta-" + String(clave).replace(/[^a-z]/g, "");

/* ---------- Formulario ---------- */
function pintarPaleta() {
  $("cc-paleta").innerHTML = paleta.map(c => `
    <button type="button" class="cta-swatch ${claseColor(c.clave)}${c.clave === colorElegido ? " activo" : ""}"
            data-color="${escapeHtml(c.clave)}" title="${escapeHtml(c.nombre)}" aria-label="${escapeHtml(c.nombre)}"
            aria-pressed="${c.clave === colorElegido}"></button>`).join("");
}

function pintarVistaPrevia() {
  const nombre = seleccion ? seleccion.nombre : "Nombre de la cuenta";
  const prefijo = $("cc-prefijo").value.trim();
  const clase = colorElegido ? claseColor(colorElegido) : "";
  $("cc-vista-previa").className = "cc-muestra fila-cta " + clase;
  $("cc-vista-previa").innerHTML =
    (prefijo ? `<span class="cta-chip">${escapeHtml(prefijo)}</span>` : "") +
    `<span>${escapeHtml(nombre)}</span>`;
}

function mostrarSeleccion() {
  const hay = Boolean(seleccion);
  $("cc-campo-buscar").classList.toggle("hidden", hay);
  $("cc-seleccionada").classList.toggle("hidden", !hay);
  $("cc-seleccionada-nombre").textContent = hay ? seleccion.nombre : "";
  pintarVistaPrevia();
}

function limpiarFormulario() {
  seleccion = null;
  colorElegido = null;
  $("cc-buscar").value = "";
  $("cc-prefijo").value = "";
  $("cc-sugerencias").classList.add("hidden");
  $("cc-titulo-form").textContent = "Etiquetar una cuenta";
  $("cc-cancelar-edicion").classList.add("hidden");
  pintarPaleta();
  mostrarSeleccion();
}

function elegirCuenta(clCuenta, nombre) {
  seleccion = { cl_cuenta: Number(clCuenta), nombre };
  $("cc-sugerencias").classList.add("hidden");
  // Si ya tenía color, se carga para poder cambiarlo.
  const previa = etiquetas.find(e => e.cl_cuenta === seleccion.cl_cuenta);
  if (previa) {
    $("cc-prefijo").value = previa.prefijo;
    colorElegido = previa.color;
    $("cc-titulo-form").textContent = "Cambiar la etiqueta de la cuenta";
    $("cc-cancelar-edicion").classList.remove("hidden");
  }
  pintarPaleta();
  mostrarSeleccion();
}

function buscarSugerencias(e) {
  clearTimeout(debounce);
  const texto = e.target.value.trim();
  const caja = $("cc-sugerencias");
  if (texto.length < 3 || !/^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]*$/.test(texto)) {
    caja.classList.add("hidden");
    caja.innerHTML = "";
    return;
  }
  debounce = setTimeout(async () => {
    try {
      const resultados = await api("/catalogos/cuentas/buscar", { params: { texto } });
      caja.innerHTML = resultados.length
        ? resultados.map(c =>
            `<div data-cl="${c.cl_cuenta}" data-nombre="${escapeHtml(c.nombre)}">${c.cl_cuenta} — ${escapeHtml(c.nombre)}</div>`
          ).join("")
        : `<div class="empty-suggestion">Sin resultados.</div>`;
      caja.classList.remove("hidden");
    } catch (err) {
      toast(err.message, "error");
    }
  }, 300);
}

async function guardar() {
  if (!seleccion) { toast("Elige primero la cuenta.", "error"); return; }
  if (!colorElegido) { toast("Elige un color.", "error"); return; }
  const btn = $("cc-guardar");
  btn.disabled = true;
  try {
    const r = await api("/admin/cuentas-etiquetas", {
      method: "PUT",
      body: { cl_cuenta: seleccion.cl_cuenta, nombre: seleccion.nombre, prefijo: $("cc-prefijo").value.trim(), color: colorElegido },
    });
    toast(r.actualizada ? "Etiqueta actualizada." : "Etiqueta guardada.", "success");
    limpiarFormulario();
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Tabla de cuentas con color ---------- */
function renderFilas() {
  $("cc-contador").textContent = etiquetas.length;
  if (!etiquetas.length) {
    $("cc-tbody").innerHTML = `<tr><td colspan="6" class="mini-empty">Todavía no hay cuentas con color.</td></tr>`;
    return;
  }
  $("cc-tbody").innerHTML = etiquetas.map((e, i) => `
    <tr class="fila-cta ${claseColor(e.color)}">
      <td data-label="#">${i + 1}</td>
      <td data-label="Cuenta">${escapeHtml(e.nombre)}</td>
      <td data-label="Etiqueta">${e.prefijo ? `<span class="cta-chip">${escapeHtml(e.prefijo)}</span>` : '<span class="muted">Sin prefijo</span>'}</td>
      <td data-label="Color">${escapeHtml(nombreColor(e.color))}</td>
      <td data-label="Última modificación">${e.actualizado ? formatDateTime(e.actualizado) : ""}${e.actualizado_por ? `<br><span class="muted">${escapeHtml(e.actualizado_por)}</span>` : ""}</td>
      <td data-label="Acciones">
        <button class="row-action-btn" data-accion="editar" data-cl="${e.cl_cuenta}">Editar</button>
        <button class="row-action-btn accion-eliminar" data-accion="quitar" data-cl="${e.cl_cuenta}">Quitar</button>
      </td>
    </tr>`).join("");
}

async function cargarGrid() {
  $("cc-tbody").innerHTML = `<tr><td colspan="6" class="mini-empty">Cargando…</td></tr>`;
  try {
    etiquetas = await api("/admin/cuentas-etiquetas");
    renderFilas();
  } catch (err) {
    $("cc-tbody").innerHTML = `<tr><td colspan="6" class="mini-empty">${escapeHtml(err.message)}</td></tr>`;
    toast(err.message, "error");
  }
}

async function quitar(clCuenta) {
  const fila = etiquetas.find(e => e.cl_cuenta === clCuenta);
  const ok = await confirmar({
    titulo: "Quitar color",
    mensaje: `¿Quitar el color${fila ? " y el prefijo de " + fila.nombre : ""}? Sus expedientes volverán a verse sin color.`,
    textoConfirmar: "Quitar",
    peligro: true,
  });
  if (!ok) return;
  try {
    await api("/admin/cuentas-etiquetas/" + encodeURIComponent(clCuenta), { method: "DELETE" });
    toast("Color quitado.", "success");
    if (seleccion && seleccion.cl_cuenta === clCuenta) limpiarFormulario();
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Ciclo de vida ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  $("cc-buscar").addEventListener("input", buscarSugerencias);
  $("cc-sugerencias").addEventListener("click", (e) => {
    const div = e.target.closest("div[data-cl]");
    if (div) elegirCuenta(div.dataset.cl, div.dataset.nombre);
  });
  $("cc-cambiar").addEventListener("click", limpiarFormulario);
  $("cc-prefijo").addEventListener("input", pintarVistaPrevia);
  $("cc-paleta").addEventListener("click", (e) => {
    const btn = e.target.closest(".cta-swatch");
    if (!btn) return;
    colorElegido = btn.dataset.color;
    pintarPaleta();
    pintarVistaPrevia();
  });
  $("cc-guardar").addEventListener("click", guardar);
  $("cc-cancelar-edicion").addEventListener("click", limpiarFormulario);
  $("cc-tbody").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-accion]");
    if (!btn) return;
    const cl = Number(btn.dataset.cl);
    if (btn.dataset.accion === "quitar") { quitar(cl); return; }
    const fila = etiquetas.find(x => x.cl_cuenta === cl);
    if (fila) {
      elegirCuenta(fila.cl_cuenta, fila.nombre);
      window.scrollTo?.(0, 0);
      contenedor.closest(".content")?.scrollTo(0, 0);
    }
  });
  limpiarFormulario();
}

export async function alEntrar() {
  try {
    if (!paleta.length) paleta = await api("/admin/cuentas-etiquetas/paleta");
  } catch (err) {
    toast(err.message, "error");
  }
  pintarPaleta();
  cargarGrid();
}

export function reiniciar() {
  etiquetas = [];
  paleta = [];
  limpiarFormulario();
  $("cc-tbody").innerHTML = "";
}
