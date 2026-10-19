/* Pantalla: Agregar cuenta (Configuración Cuentas, solo Administrador).
   Se buscan cuentas de Core y se agregan como cuentas ADICIONALES a las que ya
   se jalan en Expedientes
   (se pueden elegir varias a la vez). La lista se puede buscar, paginar,
   y quitar de una en una o todas (siempre con confirmación). */
import { api } from "../core/api.js";
import { escapeHtml } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { ICONOS } from "../componentes/iconos.js";
import { confirmar } from "../componentes/confirmar.js";
import { paginar, renderPaginador } from "../componentes/paginador.js";

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2>Agregar cuentas</h2></div>
    <div class="card-body">
      <div class="field autocomplete cfg-buscador">
        <label for="cfg-buscar-cuenta">Buscar cuenta (escribe al menos 3 letras)</label>
        <div class="cfg-input-icono">
          ${ICONOS.lupa}
          <input type="text" id="cfg-buscar-cuenta" placeholder="Nombre de la cuenta" autocomplete="off">
        </div>
        <div class="cfg-panel hidden" id="cfg-panel"></div>
      </div>
      <div class="hint cfg-nota">Las cuentas que agregues se suman a las que ya aparecen en el filtro de Cuenta de Expedientes, y también podrás darles color en Cuentas Especiales.</div>
      <div class="cfg-seleccion hidden" id="cfg-seleccion">
        <div class="cfg-seleccion-titulo">Por agregar (<span id="cfg-sel-n">0</span>)</div>
        <div class="cfg-chips" id="cfg-chips"></div>
        <div class="actions-row">
          <button class="btn btn-secondary" id="cfg-sel-limpiar">Limpiar selección</button>
          <button class="btn btn-primary" id="cfg-sel-agregar">Agregar</button>
        </div>
      </div>
    </div>
  </div>

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Cuentas adicionales (<span id="cfgCount">0</span>)</h2>
      <div class="cfg-filtro">
        ${ICONOS.lupa}
        <input type="text" id="cfg-filtro" placeholder="Filtrar por clave o nombre" autocomplete="off">
      </div>
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr><th style="width:50px;">#</th><th>Cuenta</th><th style="width:130px;">Acciones</th></tr>
        </thead>
        <tbody id="cfg-tbody"></tbody>
      </table>
    </div>
    <div class="pager" id="cfg-pager"></div>
    <div class="card-body cfg-pie">
      <span class="muted" id="cfg-pie-texto"></span>
      <button class="btn btn-danger" id="cfg-quitar-todas">Quitar todas</button>
    </div>
  </div>`;

const $ = (id) => document.getElementById(id);

let configuradas = [];          // [{cl_cuenta, nombre}]
let resultados = [];            // última búsqueda [{cl_cuenta, nombre}]
const seleccion = new Map();    // cl_cuenta -> nombre, lo que se va a agregar
let textoBuscado = "";
let indiceActivo = -1;
let paginaActual = 1;
let debounce = null;

const yaConfigurada = (cl) => configuradas.some(c => c.cl_cuenta === cl);

/* Resalta lo escrito dentro del nombre (todo se escapa antes de armar el HTML). */
function resaltar(nombre, texto) {
  if (!texto) return escapeHtml(nombre);
  const patron = new RegExp("(" + texto.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
  return nombre.split(patron).map((trozo, i) => (i % 2 ? `<mark>${escapeHtml(trozo)}</mark>` : escapeHtml(trozo))).join("");
}

/* ---------- Búsqueda y selección ---------- */
function renderPanel() {
  const panel = $("cfg-panel");
  if (!resultados.length) {
    panel.innerHTML = `<div class="cfg-vacio-panel">Sin resultados para «${escapeHtml(textoBuscado)}».</div>`;
    panel.classList.remove("hidden");
    return;
  }
  panel.innerHTML = `
    <div class="cfg-panel-cabecera">${resultados.length} resultado${resultados.length === 1 ? "" : "s"} · marca las que quieras agregar</div>
    <div class="cfg-panel-lista">` + resultados.map((c, i) => {
      const ya = yaConfigurada(c.cl_cuenta);
      const marcada = seleccion.has(c.cl_cuenta);
      return `
        <label class="cfg-op${ya ? " deshabilitada" : ""}${i === indiceActivo ? " activo" : ""}" data-i="${i}">
          <input type="checkbox" data-cl="${c.cl_cuenta}" ${marcada ? "checked" : ""} ${ya ? "disabled" : ""}>
          <span class="cuenta-chip">${escapeHtml(String(c.cl_cuenta))}</span>
          <span class="cfg-op-nombre">${resaltar(c.nombre, textoBuscado)}</span>
          ${ya ? '<span class="badge activo">Ya agregada</span>' : ""}
        </label>`;
    }).join("") + `</div>`;
  panel.classList.remove("hidden");
}

function renderSeleccion() {
  const n = seleccion.size;
  $("cfg-seleccion").classList.toggle("hidden", n === 0);
  $("cfg-sel-n").textContent = n;
  $("cfg-chips").innerHTML = [...seleccion].map(([cl, nombre]) => `
    <span class="cfg-chip">
      <span class="cuenta-chip">${escapeHtml(String(cl))}</span>${escapeHtml(nombre)}
      <button type="button" class="cfg-chip-x" data-cl="${cl}" title="Quitar de la selección" aria-label="Quitar ${escapeHtml(nombre)}">&times;</button>
    </span>`).join("");
  $("cfg-sel-agregar").textContent = n === 1 ? "Agregar 1 cuenta" : `Agregar ${n} cuentas`;
}

function alternar(cl) {
  const c = resultados.find(r => r.cl_cuenta === cl);
  if (!c || yaConfigurada(cl)) return;
  if (seleccion.has(cl)) seleccion.delete(cl);
  else seleccion.set(cl, c.nombre);
  renderSeleccion();
  renderPanel();
  // El panel se vuelve a pintar (la casilla en la que se hizo clic deja de existir):
  // el foco regresa al buscador para poder seguir con el teclado.
  $("cfg-buscar-cuenta").focus({ preventScroll: true });
}

function buscarSugerencias(e) {
  clearTimeout(debounce);
  const texto = e.target.value.trim();
  const panel = $("cfg-panel");
  const soloAlfabetico = /^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]*$/.test(texto);
  if (texto.length < 3 || !soloAlfabetico) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    resultados = [];
    return;
  }
  debounce = setTimeout(async () => {
    try {
      resultados = await api("/catalogos/cuentas/buscar", { params: { texto } });
      textoBuscado = texto;
      indiceActivo = -1;
      renderPanel();
    } catch (err) {
      toast(err.message, "error");
    }
  }, 300);
}

function moverActivo(delta) {
  if (!resultados.length) return;
  const habilitadas = resultados.map((c, i) => (yaConfigurada(c.cl_cuenta) ? -1 : i)).filter(i => i >= 0);
  if (!habilitadas.length) return;
  const pos = habilitadas.indexOf(indiceActivo);
  indiceActivo = habilitadas[(pos + delta + habilitadas.length) % habilitadas.length];
  renderPanel();
  $("cfg-panel").querySelector(".cfg-op.activo")?.scrollIntoView({ block: "nearest" });
}

function alTeclear(e) {
  if (e.key === "ArrowDown") { e.preventDefault(); moverActivo(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moverActivo(-1); }
  else if (e.key === "Enter") {
    e.preventDefault();
    if (indiceActivo >= 0 && resultados[indiceActivo]) alternar(resultados[indiceActivo].cl_cuenta);
    else if (seleccion.size) agregarSeleccionadas();
  } else if (e.key === "Escape") {
    $("cfg-panel").classList.add("hidden");
  }
}

async function agregarSeleccionadas() {
  if (!seleccion.size) return;
  const btn = $("cfg-sel-agregar");
  btn.disabled = true;
  let ok = 0;
  const fallos = [];
  for (const [cl, nombre] of seleccion) {
    try {
      await api("/configuracion/cuentas", { method: "POST", body: { cl_cuenta: cl, nombre } });
      ok++;
    } catch (err) {
      fallos.push(`${nombre}: ${err.message}`);
    }
  }
  btn.disabled = false;
  if (ok) toast(ok === 1 ? "Cuenta agregada." : `${ok} cuentas agregadas.`, "success");
  fallos.forEach(f => toast(f, "error"));
  seleccion.clear();
  resultados = [];
  $("cfg-buscar-cuenta").value = "";
  $("cfg-panel").classList.add("hidden");
  renderSeleccion();
  await cargarGrid();
}

/* ---------- Lista de cuentas configuradas ---------- */
function filtradas() {
  const t = $("cfg-filtro").value.trim().toLowerCase();
  const ordenadas = configuradas.slice().sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  if (!t) return ordenadas;
  return ordenadas.filter(c => c.nombre.toLowerCase().includes(t) || String(c.cl_cuenta).includes(t));
}

function renderConteo() {
  $("cfgCount").textContent = configuradas.length;
  $("cfg-quitar-todas").disabled = configuradas.length === 0;
}

function renderGrid() {
  renderConteo();
  const tbody = $("cfg-tbody");
  const lista = filtradas();
  $("cfg-pie-texto").textContent = configuradas.length
    ? "Estas cuentas se suman a las de siempre en el filtro de Cuenta de Expedientes y en Cuentas Especiales."
    : "";

  if (!configuradas.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="mini-empty cfg-vacio">
      <div class="cfg-vacio-icono">${ICONOS.tarjeta}</div>
      <strong>Aún no hay cuentas adicionales</strong>
      <div>Busca una cuenta arriba y agrégala a la lista.</div></td></tr>`;
    $("cfg-pager").innerHTML = "";
    return;
  }
  if (!lista.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="mini-empty">Ninguna cuenta coincide con el filtro.</td></tr>`;
    $("cfg-pager").innerHTML = "";
    return;
  }
  const pag = paginar(lista, paginaActual);
  paginaActual = pag.pagina;
  tbody.innerHTML = pag.filas.map((c, i) => `
    <tr>
      <td data-label="#">${pag.inicio + i + 1}</td>
      <td data-label="Cuenta"><span class="cuenta-chip">${escapeHtml(String(c.cl_cuenta))}</span>${escapeHtml(c.nombre)}</td>
      <td data-label="Acciones">
        <button class="row-action-btn accion-eliminar" data-accion="eliminar" data-cl="${c.cl_cuenta}">Eliminar</button>
      </td>
    </tr>`).join("");
  renderPaginador($("cfg-pager"), {
    totalFilas: lista.length,
    pagina: paginaActual,
    totalPaginas: pag.totalPaginas,
    etiqueta: "cuenta",
    alCambiar: (nueva) => { paginaActual = nueva; renderGrid(); },
  });
}

async function cargarGrid() {
  $("cfg-tbody").innerHTML = `<tr><td colspan="3" class="mini-empty">Cargando…</td></tr>`;
  try {
    configuradas = await api("/configuracion/cuentas");
  } catch (err) {
    $("cfg-tbody").innerHTML = `<tr><td colspan="3" class="mini-empty">${escapeHtml(err.message)}</td></tr>`;
    return;
  }
  renderGrid();
}

async function eliminarCuenta(clCuenta) {
  const c = configuradas.find(x => x.cl_cuenta === clCuenta);
  const ok = await confirmar({
    titulo: "Quitar cuenta",
    mensaje: `¿Quitar ${c ? c.nombre : "esta cuenta"} de las cuentas adicionales?`,
    textoConfirmar: "Eliminar",
    peligro: true,
  });
  if (!ok) return;
  try {
    await api("/configuracion/cuentas/" + clCuenta, { method: "DELETE" });
    toast("Cuenta eliminada.", "success");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function quitarTodas() {
  const n = configuradas.length;
  if (!n) return;
  const ok = await confirmar({
    titulo: "Quitar todas las cuentas",
    mensaje: `Se van a quitar las ${n} cuentas adicionales (las de siempre no se tocan). Esta acción no se puede deshacer. ¿Continuar?`,
    textoConfirmar: "Quitar todas",
    peligro: true,
  });
  if (!ok) return;
  try {
    await api("/configuracion/cuentas/limpiar", { method: "POST" });
    toast("Se quitaron todas las cuentas.", "success");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  const buscar = $("cfg-buscar-cuenta");
  buscar.addEventListener("input", buscarSugerencias);
  buscar.addEventListener("keydown", alTeclear);
  buscar.addEventListener("focus", () => { if (resultados.length) renderPanel(); });

  $("cfg-panel").addEventListener("change", (e) => {
    const cb = e.target.closest("input[type=checkbox][data-cl]");
    if (cb) alternar(Number(cb.dataset.cl));
  });
  $("cfg-chips").addEventListener("click", (e) => {
    const x = e.target.closest(".cfg-chip-x");
    if (!x) return;
    seleccion.delete(Number(x.dataset.cl));
    renderSeleccion();
    if (resultados.length) renderPanel();
  });
  $("cfg-sel-limpiar").addEventListener("click", () => {
    seleccion.clear();
    renderSeleccion();
    if (resultados.length) renderPanel();
  });
  $("cfg-sel-agregar").addEventListener("click", agregarSeleccionadas);

  $("cfg-filtro").addEventListener("input", () => { paginaActual = 1; renderGrid(); });
  $("cfg-quitar-todas").addEventListener("click", quitarTodas);
  $("cfg-tbody").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-accion]");
    if (!btn) return;
    const cl = Number(btn.dataset.cl);
    if (btn.dataset.accion === "eliminar") eliminarCuenta(cl);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#screen-configuracion .cfg-buscador")) $("cfg-panel").classList.add("hidden");
  });
  renderSeleccion();
}

export function alEntrar() {
  cargarGrid();
  $("cfg-buscar-cuenta").focus();
}

export function reiniciar() {
  configuradas = [];
  resultados = [];
  seleccion.clear();
  paginaActual = 1;
  clearTimeout(debounce);
  $("cfg-buscar-cuenta").value = "";
  $("cfg-filtro").value = "";
  $("cfg-panel").classList.add("hidden");
  renderSeleccion();
  $("cfg-tbody").innerHTML = "";
}
