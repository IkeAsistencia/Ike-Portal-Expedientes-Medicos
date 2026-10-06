/* Pantalla: Usuarios y Accesos (solo Administrador). Incluye el modal
   "Cambiar entidad" de un Proveedor. */
import { api } from "../core/api.js";
import { escapeHtml } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { NOMBRES_PERFIL, PERFIL_PROVEEDOR } from "../core/sesion.js";
import { cargarCatalogoEntidades, poblarSelectEntidades } from "../core/catalogos.js";
import { ICONOS } from "../componentes/iconos.js";
import { crearModal } from "../componentes/modal.js";

const PLANTILLA = `
  <div class="card">
    <div class="card-header"><h2>Dar de alta un nuevo acceso</h2></div>
    <div class="card-body">
      <div class="filters-grid">
        <div class="field">
          <label for="acc-rfc">RFC</label>
          <input type="text" id="acc-rfc" maxlength="20" placeholder="RFC" autocomplete="off">
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
          <input type="email" id="acc-correo" placeholder="proveedor@ejemplo.com" autocomplete="off">
        </div>
      </div>
      <div class="filters-actions">
        <button class="btn btn-primary" id="acc-dar-alta-btn">Dar de alta</button>
      </div>
      <div class="hint">La persona creará su propia contraseña la primera vez que entre con este RFC.</div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <h2>Accesos registrados (<span id="accCount">0</span>)</h2>
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr>
            <th>RFC</th><th>Nombre</th><th style="width:120px;">Perfil</th>
            <th style="width:140px;">Entidad</th>
            <th style="width:180px;">Correo</th>
            <th style="width:90px;">Estado</th>
            <th style="width:100px;">Contraseña</th><th style="width:280px;">Acciones</th>
          </tr>
        </thead>
        <tbody id="acc-tbody"></tbody>
      </table>
    </div>
  </div>`;

let modalEntidad = null;
let cambiarEntidadRfc = null;

const $ = (id) => document.getElementById(id);

/* ---------- Grid de accesos ---------- */
function botonesAcciones(a) {
  const rfc = escapeHtml(a.rfc);
  const cambiarEntidad = a.perfil === PERFIL_PROVEEDOR ? `
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
  return cambiarEntidad + resetear + activar;
}

async function cargarGrid() {
  const tbody = $("acc-tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">Cargando…</td></tr>`;
  try {
    const accesos = await api("/admin/accesos");
    $("accCount").textContent = accesos.length;
    if (!accesos.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="mini-empty">Aún no hay accesos registrados.</td></tr>`;
      return;
    }
    tbody.innerHTML = accesos.map(a => `
      <tr>
        <td data-label="RFC">${escapeHtml(a.rfc)}</td>
        <td data-label="Nombre">${escapeHtml(a.nombre)}</td>
        <td data-label="Perfil"><span class="badge perfil-${a.perfil}">${escapeHtml(NOMBRES_PERFIL[String(a.perfil)] || a.perfil)}</span></td>
        <td data-label="Entidad">${escapeHtml(a.entidad || "NA")}</td>
        <td data-label="Correo">${escapeHtml(a.correo || "NA")}</td>
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
    };
    tbody.querySelectorAll(".row-action-btn[data-accion]").forEach(btn => {
      btn.addEventListener("click", () => acciones[btn.dataset.accion](btn));
    });
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
async function accionConConfirmacion(pregunta, ruta, mensajeExito, tipoToast) {
  if (!confirm(pregunta)) return;
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
    `¿Inactivar el acceso de ${rfc}? Ya no podrá iniciar sesión, pero el registro se conserva (puedes reactivarlo después).`,
    "/admin/accesos/" + encodeURIComponent(rfc) + "/inactivar",
    "Acceso inactivado."
  );
}

function reactivar(rfc) {
  return accionConConfirmacion(
    `¿Reactivar el acceso de ${rfc}?`,
    "/admin/accesos/" + encodeURIComponent(rfc) + "/reactivar",
    "Acceso reactivado.", "success"
  );
}

function resetearPassword(rfc) {
  return accionConConfirmacion(
    `¿Resetear la contraseña de ${rfc}? Deberá crear una nueva la próxima vez que entre.`,
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

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  crearModalEntidad();

  $("acc-perfil").addEventListener("change", async (e) => {
    const esProveedor = parseInt(e.target.value, 10) === PERFIL_PROVEEDOR;
    $("acc-entidad-field").classList.toggle("hidden", !esProveedor);
    $("acc-correo-field").classList.toggle("hidden", !esProveedor);
    if (esProveedor) {
      await cargarCatalogoEntidades();
      poblarSelectEntidades($("acc-entidad"), "Selecciona una entidad");
    }
  });
  $("acc-dar-alta-btn").addEventListener("click", darDeAlta);
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
}
