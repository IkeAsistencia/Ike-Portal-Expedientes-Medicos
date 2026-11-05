/* Pantalla: Usuarios y Accesos (solo Administrador). Incluye el modal
   "Cambiar entidad" de un Proveedor y el de "Agregar perfil": una misma
   persona puede tener varios perfiles (misma contraseña) y elige con cuál
   entra en el login. */
import { api } from "../core/api.js";
import { escapeHtml } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { esCorreoDeEmpresa, MENSAJE_DOMINIO_NO_PERMITIDO } from "../core/correo-empresa.js";
import { NOMBRES_PERFIL, PERFIL_ADMINISTRADOR, PERFIL_PROVEEDOR } from "../core/sesion.js";
import { cargarCatalogoEntidades, poblarSelectEntidades } from "../core/catalogos.js";
import { ICONOS } from "../componentes/iconos.js";
import { crearModal } from "../componentes/modal.js";
import { confirmar } from "../componentes/confirmar.js";
import { paginar, renderPaginador } from "../componentes/paginador.js";

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2>Dar de alta un nuevo acceso</h2></div>
    <div class="card-body">
      <div class="filters-grid">
        <div class="field">
          <label for="acc-rfc">RFC</label>
          <input type="text" id="acc-rfc" maxlength="10" placeholder="ABCD123456" autocomplete="off"
                 aria-describedby="acc-rfc-hint">
        </div>
        <div class="field">
          <label for="acc-nombre">Nombre</label>
          <input type="text" id="acc-nombre" maxlength="120" placeholder="Nombre completo" autocomplete="off">
        </div>
        <div class="field">
          <label for="acc-perfil">Perfil</label>
          <select id="acc-perfil">
            <option value="2">Cabina</option>
            <option value="3">Proveedor</option>
            <option value="1">Administrador</option>
          </select>
        </div>
        <div class="field hidden" id="acc-entidad-field">
          <label for="acc-entidad">Entidad (obligatoria para Proveedor)</label>
          <select id="acc-entidad">
            <option value="">Selecciona una entidad</option>
          </select>
        </div>
        <div class="field hidden" id="acc-correo-field">
          <label for="acc-correo">Correo (obligatorio para Proveedor)</label>
          <input type="email" id="acc-correo" placeholder="proveedor@ikeasistencia.com" autocomplete="off">
        </div>
      </div>
      <div class="filters-actions">
        <button class="btn btn-primary" id="acc-dar-alta-btn">Dar de alta</button>
      </div>
      <!-- Debajo de la cuadrícula y no dentro del campo RFC: los campos se
           alinean por abajo y la nota subía la caja del RFC sobre las demás. -->
      <div class="hint" id="acc-rfc-hint">RFC de 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456).</div>
      <div class="hint">La persona creará su propia contraseña la primera vez que entre con este RFC.</div>
    </div>
  </div>

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Accesos registrados (<span id="accCount">…</span>)</h2>
    </div>
    <div class="card-body">
      <div class="field" style="max-width:320px;">
        <label for="acc-buscar">Buscar</label>
        <input type="text" id="acc-buscar" placeholder="Por RFC, nombre o perfil" autocomplete="off">
      </div>
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr>
            <th>RFC</th><th>Nombre</th><th style="width:150px;">Perfil</th>
            <th style="width:140px;">Entidad</th>
            <th style="width:180px;">Correo</th>
            <th style="width:90px;">Estado</th>
            <th style="width:100px;">Contraseña</th><th style="width:280px;">Acciones</th>
          </tr>
        </thead>
        <tbody id="acc-tbody"></tbody>
      </table>
    </div>
    <div class="pager" id="acc-pager"></div>
  </div>`;

let modalEntidad = null;
let cambiarEntidadRfc = null;
let modalPerfil = null;
let agregarPerfilRfc = null;
let accesosActuales = [];
let paginaActual = 1;

const $ = (id) => document.getElementById(id);

/* ---------- Grid de accesos ---------- */
const PERFILES_ORDEN_ALTA = [2, 3, 1]; // mismo orden que el combo del alta: Cabina, Proveedor, Administrador

function perfilesDe(a) {
  return a.perfiles && a.perfiles.length ? a.perfiles : [a.perfil];
}

function perfilesQueFaltan(a) {
  const tiene = perfilesDe(a);
  return PERFILES_ORDEN_ALTA.filter(p => !tiene.includes(p));
}

/* Una insignia por perfil; con más de uno, cada una trae su "×" para quitarlo. */
function celdaPerfiles(a) {
  const perfiles = perfilesDe(a);
  return perfiles.map(p => {
    const nombre = escapeHtml(NOMBRES_PERFIL[String(p)] || p);
    const quitar = perfiles.length > 1 ? `
      <button type="button" class="badge-quitar" data-quitar-perfil="${p}" data-rfc="${escapeHtml(a.rfc)}"
        title="Quitar el perfil ${nombre}" aria-label="Quitar el perfil ${nombre}">×</button>` : "";
    return `<span class="badge perfil-${p}">${nombre}${quitar}</span>`;
  }).join(" ");
}

function botonesAcciones(a) {
  const rfc = escapeHtml(a.rfc);
  const agregarPerfil = perfilesQueFaltan(a).length ? `
    <button class="row-action-btn accion-reset" data-accion="agregar-perfil" data-rfc="${rfc}" title="Darle otro perfil a esta persona: misma contraseña, y al entrar elige con cuál">
      ${ICONOS.palomita} Agregar perfil
    </button>` : "";
  const cambiarEntidad = perfilesDe(a).includes(PERFIL_PROVEEDOR) ? `
    <button class="row-action-btn accion-reset" data-accion="cambiar-entidad" data-rfc="${rfc}" data-entidad="${escapeHtml(a.entidad || "")}" title="Cambiar la entidad asignada a este Proveedor">
      ${ICONOS.ubicacion} Cambiar entidad
    </button>` : "";
  const resetear = `
    <button class="row-action-btn accion-reset" data-accion="reset" data-rfc="${rfc}" title="La persona tendrá que crear una contraseña nueva la próxima vez que entre">
      ${ICONOS.reiniciar} Resetear contraseña
    </button>`;
  const activar = a.activo ? `
    <button class="row-action-btn accion-eliminar" data-accion="inactivar" data-rfc="${rfc}" title="La persona ya no podrá iniciar sesión, pero el registro se conserva">
      ${ICONOS.prohibido} Inactivar
    </button>` : `
    <button class="row-action-btn accion-reset" data-accion="reactivar" data-rfc="${rfc}" title="La persona vuelve a poder iniciar sesión">
      ${ICONOS.palomita} Reactivar
    </button>`;
  return agregarPerfil + cambiarEntidad + resetear + activar;
}

function accesosFiltrados() {
  const texto = $("acc-buscar").value.trim().toLowerCase();
  if (!texto) return accesosActuales;
  return accesosActuales.filter(a =>
    a.rfc.toLowerCase().includes(texto) ||
    a.nombre.toLowerCase().includes(texto) ||
    perfilesDe(a).some(p => (NOMBRES_PERFIL[String(p)] || "").toLowerCase().includes(texto))
  );
}

/* El backend guarda "NA" (SIN_APLICA, ver accesos_repo.py) para los campos
   que no aplican a un perfil (ej. entidad de un Administrador). En la grilla
   se muestra "—", igual que en el resto del portal. */
function sinAplica(valor) {
  const texto = (valor || "").trim();
  return !texto || texto.toUpperCase() === "NA" ? "—" : texto;
}

function renderGrid() {
  const tbody = $("acc-tbody");
  const filtrados = accesosFiltrados();
  $("accCount").textContent = filtrados.length;

  if (!accesosActuales.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">Aún no hay accesos registrados.</td></tr>`;
    $("acc-pager").innerHTML = "";
    return;
  }
  if (!filtrados.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">Ningún acceso coincide con tu búsqueda.</td></tr>`;
    $("acc-pager").innerHTML = "";
    return;
  }

  const pag = paginar(filtrados, paginaActual);
  paginaActual = pag.pagina;

  tbody.innerHTML = pag.filas.map(a => `
    <tr>
      <td data-label="RFC">${escapeHtml(a.rfc)}</td>
      <td data-label="Nombre">${escapeHtml(a.nombre)}</td>
      <td data-label="Perfil">${celdaPerfiles(a)}</td>
      <td data-label="Entidad">${escapeHtml(sinAplica(a.entidad))}</td>
      <td data-label="Correo">${escapeHtml(sinAplica(a.correo))}</td>
      <td data-label="Estado"><span class="badge ${a.activo ? "activo" : "inactivo"}">${a.activo ? "Activo" : "Inactivo"}</span></td>
      <td data-label="Contraseña">${a.tiene_password ? '<span class="muted">Ya creada</span>' : '<span class="muted">Pendiente</span>'}</td>
      <td data-label="Acciones">
        <div style="display:flex;gap:6px;flex-wrap:wrap;">${botonesAcciones(a)}</div>
      </td>
    </tr>
  `).join("");

  const acciones = {
    "inactivar": (btn) => inactivar(btn.dataset.rfc),
    "reactivar": (btn) => reactivar(btn.dataset.rfc),
    "reset": (btn) => resetearPassword(btn.dataset.rfc),
    "cambiar-entidad": (btn) => abrirModalCambiarEntidad(btn.dataset.rfc, btn.dataset.entidad),
    "agregar-perfil": (btn) => abrirModalAgregarPerfil(btn.dataset.rfc),
  };
  tbody.querySelectorAll(".row-action-btn[data-accion]").forEach(btn => {
    btn.addEventListener("click", () => acciones[btn.dataset.accion](btn));
  });
  tbody.querySelectorAll("[data-quitar-perfil]").forEach(btn => {
    btn.addEventListener("click", () => quitarPerfil(btn.dataset.rfc, Number(btn.dataset.quitarPerfil)));
  });

  renderPaginador($("acc-pager"), {
    totalFilas: filtrados.length,
    pagina: paginaActual,
    totalPaginas: pag.totalPaginas,
    etiqueta: "usuario",
    alCambiar: (nueva) => {
      paginaActual = nueva;
      renderGrid();
    },
  });
}

async function cargarGrid() {
  const tbody = $("acc-tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">Cargando…</td></tr>`;
  try {
    accesosActuales = await api("/admin/accesos");
    paginaActual = 1;
    renderGrid();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">${escapeHtml(err.message)}</td></tr>`;
  }
}

/* ---------- Alta ---------- */
async function darDeAlta() {
  const rfc = $("acc-rfc").value.trim().toUpperCase();
  const nombre = $("acc-nombre").value.trim();
  const perfil = parseInt($("acc-perfil").value, 10);
  const entidad = $("acc-entidad").value;
  const correo = $("acc-correo").value.trim();
  if (!rfc || !nombre) {
    toast("Ingresa el RFC y el nombre.", "error");
    return;
  }
  if (!/^[A-Z]{4}\d{6}$/.test(rfc)) {
    toast("El RFC debe tener 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456).", "error");
    return;
  }
  if (perfil === PERFIL_PROVEEDOR && !entidad) {
    toast("Debes asignarle una entidad al perfil Proveedor.", "error");
    return;
  }
  if (perfil === PERFIL_PROVEEDOR && !correo) {
    toast("Debes asignarle un correo al perfil Proveedor.", "error");
    return;
  }
  if (perfil === PERFIL_PROVEEDOR && !esCorreoDeEmpresa(correo)) {
    toast(MENSAJE_DOMINIO_NO_PERMITIDO, "error");
    return;
  }
  const btn = $("acc-dar-alta-btn");
  btn.disabled = true;
  try {
    await api("/admin/accesos", {
      method: "POST",
      body: { rfc, nombre, perfil, entidad: entidad || undefined, correo: correo || undefined },
    });
    toast("Acceso creado. La persona ya puede entrar y crear su contraseña.", "success");
    $("acc-rfc").value = "";
    $("acc-nombre").value = "";
    $("acc-entidad").value = "";
    $("acc-correo").value = "";
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Acciones por fila ---------- */
async function accionConConfirmacion({ titulo, pregunta, textoConfirmar, peligro }, ruta, mensajeExito, tipoToast) {
  if (!(await confirmar({ titulo, mensaje: pregunta, textoConfirmar, peligro }))) return;
  try {
    await api(ruta, { method: "POST" });
    toast(mensajeExito, tipoToast);
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

function inactivar(rfc) {
  return accionConConfirmacion(
    {
      titulo: "Inactivar acceso",
      pregunta: `¿Inactivar el acceso de ${rfc}? Ya no podrá iniciar sesión, pero el registro se conserva (puedes reactivarlo después).`,
      textoConfirmar: "Inactivar",
      peligro: true,
    },
    "/admin/accesos/" + encodeURIComponent(rfc) + "/inactivar",
    "Acceso inactivado."
  );
}

function reactivar(rfc) {
  return accionConConfirmacion(
    { titulo: "Reactivar acceso", pregunta: `¿Reactivar el acceso de ${rfc}?`, textoConfirmar: "Reactivar" },
    "/admin/accesos/" + encodeURIComponent(rfc) + "/reactivar",
    "Acceso reactivado.", "success"
  );
}

function resetearPassword(rfc) {
  return accionConConfirmacion(
    {
      titulo: "Resetear contraseña",
      pregunta: `¿Resetear la contraseña de ${rfc}? Deberá crear una nueva la próxima vez que entre.`,
      textoConfirmar: "Resetear",
      peligro: true,
    },
    "/admin/accesos/" + encodeURIComponent(rfc) + "/resetear-password",
    "Contraseña reseteada."
  );
}

/* ---------- Modal: Cambiar entidad (Proveedor) ---------- */
function crearModalEntidad() {
  modalEntidad = crearModal({
    id: "cambiar-entidad-modal-overlay",
    titulo: "Cambiar entidad",
    ancho: "420px",
    cuerpo: `
      <p id="cambiar-entidad-modal-rfc"></p>
      <div class="field">
        <label for="cambiar-entidad-select">Nueva entidad</label>
        <select id="cambiar-entidad-select">
          <option value="">Selecciona una entidad</option>
        </select>
      </div>`,
    pie: `
      <button class="btn btn-secondary" id="cambiar-entidad-modal-cancelar">Cancelar</button>
      <button class="btn btn-primary" id="cambiar-entidad-modal-guardar">Guardar</button>`,
    alCerrar: () => { cambiarEntidadRfc = null; },
  });
  $("cambiar-entidad-modal-cancelar").addEventListener("click", () => modalEntidad.cerrar());
  $("cambiar-entidad-modal-guardar").addEventListener("click", guardarEntidad);
}

async function abrirModalCambiarEntidad(rfc, entidadActual) {
  cambiarEntidadRfc = rfc;
  $("cambiar-entidad-modal-rfc").textContent = `RFC: ${rfc} — entidad actual: ${entidadActual || "NA"}`;
  await cargarCatalogoEntidades();
  poblarSelectEntidades($("cambiar-entidad-select"), "Selecciona una entidad");
  $("cambiar-entidad-select").value = entidadActual || "";
  modalEntidad.abrir();
}

async function guardarEntidad() {
  if (!cambiarEntidadRfc) return;
  const entidad = $("cambiar-entidad-select").value;
  if (!entidad) {
    toast("Selecciona una entidad.", "error");
    return;
  }
  const btn = $("cambiar-entidad-modal-guardar");
  btn.disabled = true;
  try {
    await api("/admin/accesos/" + encodeURIComponent(cambiarEntidadRfc) + "/entidad", {
      method: "POST",
      body: { entidad },
    });
    toast("Entidad actualizada.", "success");
    modalEntidad.cerrar();
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Agregar / quitar un perfil de una persona que ya tiene acceso ---------- */
function crearModalPerfil() {
  modalPerfil = crearModal({
    id: "agregar-perfil-modal-overlay",
    titulo: "Agregar perfil",
    ancho: "420px",
    cuerpo: `
      <p id="agregar-perfil-modal-rfc"></p>
      <div class="field">
        <label for="agregar-perfil-select">Perfil</label>
        <select id="agregar-perfil-select"></select>
      </div>
      <div class="field hidden" id="agregar-perfil-entidad-field">
        <label for="agregar-perfil-entidad">Entidad (obligatoria para Proveedor)</label>
        <select id="agregar-perfil-entidad">
          <option value="">Selecciona una entidad</option>
        </select>
      </div>
      <div class="field hidden" id="agregar-perfil-correo-field">
        <label for="agregar-perfil-correo">Correo (obligatorio para Proveedor)</label>
        <input type="email" id="agregar-perfil-correo" placeholder="proveedor@ikeasistencia.com" autocomplete="off">
      </div>
      <div class="hint">Entra con el mismo RFC y la misma contraseña; en el login elige con qué perfil.</div>`,
    pie: `
      <button class="btn btn-secondary" id="agregar-perfil-modal-cancelar">Cancelar</button>
      <button class="btn btn-primary" id="agregar-perfil-modal-guardar">Agregar</button>`,
    alCerrar: () => { agregarPerfilRfc = null; },
  });
  $("agregar-perfil-modal-cancelar").addEventListener("click", () => modalPerfil.cerrar());
  $("agregar-perfil-modal-guardar").addEventListener("click", guardarPerfil);
  $("agregar-perfil-select").addEventListener("change", mostrarCamposProveedor);
}

async function mostrarCamposProveedor() {
  const esProveedor = parseInt($("agregar-perfil-select").value, 10) === PERFIL_PROVEEDOR;
  $("agregar-perfil-entidad-field").classList.toggle("hidden", !esProveedor);
  $("agregar-perfil-correo-field").classList.toggle("hidden", !esProveedor);
  if (esProveedor) {
    await cargarCatalogoEntidades();
    poblarSelectEntidades($("agregar-perfil-entidad"), "Selecciona una entidad");
  }
}

function abrirModalAgregarPerfil(rfc) {
  const acceso = accesosActuales.find(a => a.rfc === rfc);
  if (!acceso) return;
  agregarPerfilRfc = rfc;
  $("agregar-perfil-modal-rfc").textContent = `RFC: ${rfc} — ${acceso.nombre}`;
  $("agregar-perfil-select").innerHTML = perfilesQueFaltan(acceso)
    .map(p => `<option value="${p}">${escapeHtml(NOMBRES_PERFIL[String(p)])}</option>`)
    .join("");
  $("agregar-perfil-entidad").value = "";
  $("agregar-perfil-correo").value = "";
  mostrarCamposProveedor();
  modalPerfil.abrir();
}

async function guardarPerfil() {
  if (!agregarPerfilRfc) return;
  const perfil = parseInt($("agregar-perfil-select").value, 10);
  const entidad = $("agregar-perfil-entidad").value;
  const correo = $("agregar-perfil-correo").value.trim();
  if (perfil === PERFIL_PROVEEDOR && (!entidad || !correo)) {
    toast("Para el perfil Proveedor captura la entidad y el correo.", "error");
    return;
  }
  if (perfil === PERFIL_PROVEEDOR && !esCorreoDeEmpresa(correo)) {
    toast(MENSAJE_DOMINIO_NO_PERMITIDO, "error");
    return;
  }
  const btn = $("agregar-perfil-modal-guardar");
  btn.disabled = true;
  try {
    await api("/admin/accesos/" + encodeURIComponent(agregarPerfilRfc) + "/perfiles", {
      method: "POST",
      body: { perfil, entidad: entidad || undefined, correo: correo || undefined },
    });
    toast("Perfil agregado. Al entrar, la persona elegirá con cuál.", "success");
    modalPerfil.cerrar();
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function quitarPerfil(rfc, perfil) {
  const nombre = NOMBRES_PERFIL[String(perfil)] || perfil;
  if (!(await confirmar({
    titulo: "Quitar perfil",
    mensaje: `¿Quitarle el perfil ${nombre} a ${rfc}? Seguirá entrando con sus otros perfiles.`,
    textoConfirmar: "Quitar",
    peligro: true,
  }))) return;
  try {
    await api("/admin/accesos/" + encodeURIComponent(rfc) + "/perfiles/" + perfil, { method: "DELETE" });
    toast(`Perfil ${nombre} quitado.`, "success");
    cargarGrid();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  crearModalEntidad();
  crearModalPerfil();

  $("acc-perfil").addEventListener("change", async (e) => {
    const perfil = parseInt(e.target.value, 10);
    const esProveedor = perfil === PERFIL_PROVEEDOR;
    $("acc-entidad-field").classList.toggle("hidden", !esProveedor);
    $("acc-correo-field").classList.toggle("hidden", !esProveedor);
    if (esProveedor) {
      await cargarCatalogoEntidades();
      poblarSelectEntidades($("acc-entidad"), "Selecciona una entidad");
    }
  });
  $("acc-dar-alta-btn").addEventListener("click", darDeAlta);
  $("acc-buscar").addEventListener("input", () => {
    paginaActual = 1;
    renderGrid();
  });
  ["acc-rfc", "acc-nombre"].forEach(id => {
    $(id).addEventListener("keydown", (e) => {
      // .click() y no darDeAlta(): si el botón está deshabilitado (alta en
      // curso), el clic no hace nada y no se manda dos veces.
      if (e.key === "Enter") { e.preventDefault(); $("acc-dar-alta-btn").click(); }
    });
  });
}

export function alEntrar() {
  cargarGrid();
  $("acc-rfc").focus();
}

export function reiniciar() {
  modalEntidad.cerrar();
  modalPerfil.cerrar();
}
