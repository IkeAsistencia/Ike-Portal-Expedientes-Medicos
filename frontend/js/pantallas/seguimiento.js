/* Pantalla: Seguimiento de expedientes (detalle de un expediente,
   comentarios, estatus y registro de seguimiento del Proveedor). */
import { api, apiArchivo } from "../core/api.js";
import { escapeHtml, formatDate, formatDateTime } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { navegar } from "../core/router.js";
import { esPerfilCabina, esPerfilProveedor } from "../core/sesion.js";
import {
  ESTATUS_ACCIONABLES_PROVEEDOR, ESTATUS_DE_REGRESO, notificarCambioEstatus, proveedorPuedeVer,
} from "../core/reglas-expedientes.js";
import { ICONOS } from "../componentes/iconos.js";

const PLANTILLA = `
  <div class="card" id="sg-buscar-card">
    <div class="card-header"><h2>Buscar expediente</h2></div>
    <div class="card-body">
      <div class="estatus-row">
        <div class="field">
          <label for="sg-buscar-expediente">Número de expediente</label>
          <input type="number" id="sg-buscar-expediente">
        </div>
        <button class="btn btn-primary" id="sg-buscar-btn">Buscar</button>
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-info-card">
    <div class="card-header"><h2>Información General</h2></div>
    <div class="card-body">
      <div class="info-grid">
        <div class="info-item"><label>Expediente</label><div class="value" id="ig-expediente">—</div></div>
        <div class="info-item"><label>Fecha Apertura</label><div class="value" id="ig-fechaApertura">—</div></div>
        <div class="info-item"><label>Nombre del Titular</label><div class="value" id="ig-titular">—</div></div>
        <div class="info-item"><label>Nombre del Paciente</label><div class="value" id="ig-paciente">—</div></div>
        <div class="info-item"><label>Entidad</label><div class="value" id="ig-entidad">—</div></div>
        <div class="info-item"><label>Municipio</label><div class="value" id="ig-municipio">—</div></div>
        <div class="info-item"><label>Teléfono</label><div class="value" id="ig-telefono">—</div></div>
        <div class="info-item"><label>Correo</label><div class="value" id="ig-correo">—</div></div>
      </div>
      <div class="field" style="margin-top:14px;padding-top:14px;border-top:1px solid var(--gray-border);">
        <label style="display:flex;align-items:center;gap:8px;font-weight:normal;cursor:pointer;">
          <input type="checkbox" id="ig-pago-anticipado" style="width:auto;">
          ¿Es un expediente de pago anticipado?
        </label>
        <div class="hint" id="ig-pago-anticipado-hint">Solo el Proveedor puede marcar esta casilla.</div>
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-comentarios-proveedor-card">
    <div class="card-header"><h2>Comentarios del Proveedor</h2></div>
    <div class="card-body">
      <div id="sg-comentarios-proveedor-lista"></div>
      <div class="hidden" id="sg-comprobante-visor-wrap" style="margin-top:14px;padding-top:14px;border-top:1px solid var(--gray-border);">
        <label style="display:block;font-size:11px;font-weight:600;color:var(--navy);margin-bottom:6px;">Comprobante de pago</label>
        <div id="sg-comprobante-visor"></div>
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-comentarios-coordinador-card">
    <div class="card-header"><h2>Comentarios del Coordinador</h2></div>
    <div class="card-body">
      <div id="sg-comentarios-coordinador-lista"></div>
    </div>
  </div>

  <div class="card hidden" id="sg-estatus-card">
    <div class="card-header"><h2>Estado del Caso</h2></div>
    <div class="card-body">
      <div class="estatus-row">
        <div class="field">
          <label for="sg-estatus">Estado</label>
          <select id="sg-estatus">
            <option value="Abierto">Abierto</option>
            <option value="Finalizado">Finalizado</option>
            <option value="En Espera de Respuesta">Regresar a Proveedor (corregir respuesta)</option>
            <option value="Seguimiento de Cita" id="sg-estatus-opcion-cita" class="hidden">Seguimiento de Cita (cita aceptada)</option>
          </select>
        </div>
        <button class="btn btn-secondary" id="sg-estatus-btn">Actualizar Estado</button>
      </div>
      <div class="field hidden" id="sg-motivo-regreso-field" style="margin-top:12px;">
        <label for="sg-motivo-regreso" id="sg-motivo-regreso-label">Motivo del regreso (obligatorio)</label>
        <textarea id="sg-motivo-regreso" rows="4" maxlength="1500" placeholder="Explica qué le falta o qué está mal en la respuesta del proveedor..."></textarea>
        <div class="hint">Se guarda en Core igual que el comentario del proveedor, y se le notifica por correo.</div>
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-seguimiento-card">
    <div class="card-header"><h2>Registrar seguimiento</h2></div>
    <div class="card-body">
      <div class="notif-banner notif-success hidden" id="sg-exito-banner">
        ${ICONOS.exito}
        <span>Comentario enviado correctamente a la bitácora de seguimiento.</span>
      </div>
      <div class="field">
        <label for="sg-observaciones">Observaciones</label>
        <textarea id="sg-observaciones" rows="7" maxlength="1500"></textarea>
        <div class="char-counter" id="sg-counter">0 / 1500</div>
        <div class="hint">Cada vez que presionas "Actualizar Core" se guarda un nuevo registro en la bitácora de seguimiento, no se sobrescribe el anterior.</div>
      </div>
      <div class="field hidden" id="sg-comprobante-field">
        <label for="sg-comprobante-input">Comprobante de pago (obligatorio para Pago Anticipado)</label>
        <input type="file" id="sg-comprobante-input" accept=".pdf,.jpg,.jpeg,.png">
        <div class="hint">Formatos permitidos: PDF, JPG o PNG. Tamaño máximo 5 MB.</div>
      </div>
      <div class="actions-row">
        <button class="btn btn-secondary" id="sg-cancelar-btn">Cancelar</button>
        <button class="btn btn-primary" id="sg-actualizar-btn">Actualizar Core</button>
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-solo-lectura-card">
    <div class="card-body">
      <div class="notif-banner">
        Ya enviaste tu seguimiento para este expediente y está en revisión por el coordinador.
        Puedes ver tus comentarios y tu comprobante abajo, pero no puedes registrar nada más
        hasta que el coordinador lo revise.
      </div>
    </div>
  </div>

  <div class="card hidden" id="sg-regresar-card">
    <div class="card-body">
      <button class="btn btn-secondary" id="sg-regresar-btn">Regresar</button>
    </div>
  </div>`;

const COMPROBANTE_TAMANO_MAXIMO = 5 * 1024 * 1024; // 5 MB
const COMPROBANTE_TIPOS_PERMITIDOS = ["application/pdf", "image/jpeg", "image/png"];
const COMENTARIO_PROVEEDOR_MINIMO = 50;

let registroActual = null;
let pagoAnticipadoActual = { es_anticipado: false, bloqueado: false }; // del expediente abierto actualmente, ver cargarPagoAnticipado()

const $ = (id) => document.getElementById(id);

/* ---------- Abrir / cerrar ---------- */

/* Clic en "Seguimiento de expedientes" del menú: arranca en blanco, con el buscador. */
export function abrirDesdeMenu() {
  $("sg-buscar-card").classList.remove("hidden");
  $("sg-buscar-expediente").disabled = false;
  $("sg-buscar-expediente").value = "";
  ocultarPaneles();
  navegar("seguimiento");
}

function ocultarPaneles() {
  ["sg-info-card", "sg-estatus-card", "sg-seguimiento-card", "sg-solo-lectura-card",
    "sg-comentarios-proveedor-card", "sg-comentarios-coordinador-card", "sg-regresar-card",
  ].forEach(id => $(id).classList.add("hidden"));
  registroActual = null;
}

/* source: "link" (clic en el número de expediente de una tabla) o "menu"
   (se buscó desde esta misma pantalla). */
export async function abrirSeguimiento(record, source) {
  navegar("seguimiento");
  registroActual = record;

  const buscarCard = $("sg-buscar-card");
  if (source === "link") {
    buscarCard.classList.add("hidden");
  } else {
    buscarCard.classList.remove("hidden");
    $("sg-buscar-expediente").value = record.expediente;
    $("sg-buscar-expediente").disabled = true;
  }

  $("ig-expediente").textContent = record.expediente;
  $("ig-fechaApertura").textContent = formatDate(record.fecha_apertura_servicio);
  $("ig-titular").textContent = record.nombre_titular || "—";
  $("ig-paciente").textContent = record.nombre_paciente || "—";
  $("ig-entidad").textContent = record.entidad || "—";
  $("ig-municipio").textContent = record.municipio || "—";
  $("ig-telefono").textContent = record.telefono || "—";
  $("ig-correo").textContent = record.email || "—";

  $("sg-estatus").value = record.estatus;
  $("sg-motivo-regreso").value = "";
  $("sg-motivo-regreso-field").classList.toggle("hidden", !ESTATUS_DE_REGRESO.includes(record.estatus));
  actualizarTextoMotivoRegreso(record.estatus);
  $("sg-observaciones").value = "";
  $("sg-observaciones").disabled = false;
  $("sg-cancelar-btn").disabled = false;
  $("sg-actualizar-btn").disabled = false;
  $("sg-exito-banner").classList.add("hidden");
  $("sg-comprobante-input").value = "";
  $("sg-comprobante-input").disabled = false;
  actualizarContador();

  $("sg-info-card").classList.remove("hidden");
  $("sg-estatus-card").classList.remove("hidden");
  $("sg-regresar-card").classList.remove("hidden");

  // Proveedor solo puede registrar seguimiento mientras el expediente está
  // "En Espera de Respuesta" -- si ya lo mandó (quedó "Seguimiento
  // Proveedor"), lo puede seguir viendo pero en modo solo lectura, hasta
  // que el coordinador lo revise (lo regrese o lo finalice).
  const proveedorSoloLectura = esPerfilProveedor() && !ESTATUS_ACCIONABLES_PROVEEDOR.includes(record.estatus);
  $("sg-seguimiento-card").classList.toggle("hidden", proveedorSoloLectura);
  $("sg-solo-lectura-card").classList.toggle("hidden", !proveedorSoloLectura);

  // Comentarios (del Proveedor y del Coordinador): visibles para ambos
  // perfiles, sin importar por dónde se entró a este expediente.
  $("sg-comentarios-proveedor-card").classList.remove("hidden");
  $("sg-comentarios-coordinador-card").classList.remove("hidden");
  cargarComentarios(record.expediente);

  await cargarPagoAnticipado(record);
}

async function buscarExpediente() {
  const val = $("sg-buscar-expediente").value;
  if (!val) { toast("Ingresa un número de expediente.", "error"); return; }
  try {
    const data = await api("/expedientes", { params: { cl_expediente: val } });
    if (!data.length || !proveedorPuedeVer(data[0].estatus)) {
      toast("No se encontró el expediente " + val + ".", "error");
      ocultarPaneles();
      return;
    }
    abrirSeguimiento(data[0], "menu");
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Pago anticipado y comprobante ---------- */
async function cargarPagoAnticipado(record) {
  const chk = $("ig-pago-anticipado");
  let flag = { es_anticipado: false, bloqueado: false };
  try {
    flag = await api("/seguimiento/pago-anticipado/" + record.expediente);
  } catch (err) {
    toast("No se pudo cargar si es pago anticipado: " + err.message, "error");
  }
  pagoAnticipadoActual = flag;

  chk.checked = flag.es_anticipado;
  chk.disabled = !(esPerfilProveedor() && !flag.bloqueado);
  $("ig-pago-anticipado-hint").textContent = flag.bloqueado
    ? "Ya no se puede cambiar: el expediente ya fue enviado."
    : (esPerfilProveedor() ? "Márcala antes de mandar tu primer comentario -- después ya no se puede cambiar." : "Solo el Proveedor puede marcar esta casilla.");

  // "Seguimiento de Cita" solo aplica (y solo se ve) si es pago anticipado.
  $("sg-estatus-opcion-cita").classList.toggle("hidden", !flag.es_anticipado);
  if ($("sg-estatus").value === "Seguimiento de Cita" && !flag.es_anticipado) {
    $("sg-estatus").value = record.estatus;
  }

  // El comprobante de pago solo se pide hasta que Cabina regresó el
  // expediente como "Seguimiento de Cita" (cita ya aceptada) -- no antes.
  const necesitaComprobante = flag.es_anticipado && record.estatus === "Seguimiento de Cita";
  $("sg-comprobante-field").classList.toggle("hidden", !(necesitaComprobante && esPerfilProveedor()));

  // Comprobante de pago (solo Pago Anticipado): Cabina lo revisa y Proveedor
  // puede volver a verlo/descargarlo si ya subió uno antes.
  $("sg-comprobante-visor-wrap").classList.toggle("hidden", !flag.es_anticipado);
  if (flag.es_anticipado) cargarComprobanteVisor(record.expediente);
}

async function cambiarPagoAnticipado(e) {
  const chk = e.target;
  const valorAnterior = !chk.checked;
  chk.disabled = true;
  try {
    await api("/seguimiento/pago-anticipado/" + registroActual.expediente, {
      method: "POST",
      body: { es_anticipado: chk.checked },
    });
    toast("Guardado.", "success");
    await cargarPagoAnticipado(registroActual);
  } catch (err) {
    chk.checked = valorAnterior;
    chk.disabled = false;
    toast(err.message, "error");
  }
}

async function cargarComprobanteVisor(clExpediente) {
  const cont = $("sg-comprobante-visor");
  cont.innerHTML = `<div class="mini-empty">Cargando…</div>`;
  try {
    const meta = await api("/seguimiento/comprobante/" + clExpediente);
    cont.innerHTML = `
      <div class="comentario-item">
        <div class="comentario-meta"><span>${escapeHtml(meta.rfc)}</span><span>${formatDateTime(meta.fecha)}</span></div>
        <div class="comentario-texto">${escapeHtml(meta.nombre_archivo)}</div>
        <button class="btn btn-secondary" style="margin-top:8px;" id="sg-comprobante-ver-btn">Ver / Descargar</button>
      </div>`;
    $("sg-comprobante-ver-btn").addEventListener("click", () => verComprobante(clExpediente));
  } catch (err) {
    cont.innerHTML = `<div class="mini-empty">El proveedor todavía no ha subido el comprobante de pago.</div>`;
  }
}

async function verComprobante(clExpediente) {
  try {
    const { blob } = await apiArchivo(
      "/seguimiento/comprobante/" + clExpediente + "/archivo",
      "No se pudo abrir el comprobante."
    );
    window.open(URL.createObjectURL(blob), "_blank");
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Comentarios ---------- */
function renderListaComentarios(contId, comentarios, mensajeVacio) {
  const cont = $(contId);
  if (!comentarios.length) {
    cont.innerHTML = `<div class="mini-empty">${mensajeVacio}</div>`;
    return;
  }
  cont.innerHTML = comentarios.map(c => `
    <div class="comentario-item">
      <div class="comentario-meta"><span>${escapeHtml(c.rfc)}</span><span>${formatDateTime(c.fecha)}</span></div>
      <div class="comentario-texto">${escapeHtml(c.comentario)}</div>
    </div>
  `).join("");
}

async function cargarComentarios(clExpediente) {
  $("sg-comentarios-proveedor-lista").innerHTML = `<div class="mini-empty">Cargando…</div>`;
  $("sg-comentarios-coordinador-lista").innerHTML = `<div class="mini-empty">Cargando…</div>`;
  try {
    const comentarios = await api("/seguimiento/comentarios/" + clExpediente);
    renderListaComentarios(
      "sg-comentarios-proveedor-lista",
      comentarios.filter(c => c.origen !== "cabina"),
      "El proveedor todavía no ha registrado ningún comentario para este expediente."
    );
    renderListaComentarios(
      "sg-comentarios-coordinador-lista",
      comentarios.filter(c => c.origen === "cabina"),
      "El coordinador no ha regresado este expediente."
    );
  } catch (err) {
    $("sg-comentarios-proveedor-lista").innerHTML = `<div class="mini-empty">${escapeHtml(err.message)}</div>`;
    $("sg-comentarios-coordinador-lista").innerHTML = `<div class="mini-empty">${escapeHtml(err.message)}</div>`;
  }
}

/* ---------- Estado del caso (Cabina) ---------- */
function actualizarTextoMotivoRegreso(estatus) {
  const label = $("sg-motivo-regreso-label");
  const textarea = $("sg-motivo-regreso");
  if (estatus === "Seguimiento de Cita") {
    label.textContent = "Comentario (obligatorio)";
    textarea.placeholder = "Ej. Se acepta la cita, el paciente puede proceder...";
  } else {
    label.textContent = "Motivo del regreso (obligatorio)";
    textarea.placeholder = "Explica qué le falta o qué está mal en la respuesta del proveedor...";
  }
}

async function actualizarEstatus() {
  if (!registroActual) return;
  const nuevoEstatus = $("sg-estatus").value;
  const esRegreso = ESTATUS_DE_REGRESO.includes(nuevoEstatus);
  const motivoRegreso = $("sg-motivo-regreso").value.trim();
  if (esRegreso && !motivoRegreso) {
    toast("Indica un comentario para regresar el expediente al proveedor.", "error");
    return;
  }
  try {
    await api("/seguimiento/estatus", {
      method: "POST",
      body: {
        cl_expediente: registroActual.expediente,
        estatus: nuevoEstatus,
        comentario: esRegreso ? motivoRegreso : undefined,
      },
    });
    registroActual.estatus = nuevoEstatus;
    notificarCambioEstatus(registroActual.expediente, nuevoEstatus);
    if (esRegreso) {
      $("sg-motivo-regreso").value = "";
      $("sg-motivo-regreso-field").classList.add("hidden");
      // Para que el comentario que se acaba de mandar se vea de inmediato en
      // "Comentarios del Coordinador", sin tener que refrescar la página.
      cargarComentarios(registroActual.expediente);
      // El comprobante se activa (o no) según el nuevo estatus.
      cargarPagoAnticipado(registroActual);
      toast("Expediente regresado a Proveedor. Se le notificó por correo.", "success");
    } else {
      toast("Estado actualizado.", "success");
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Registrar seguimiento (Proveedor) ---------- */
function actualizarContador() {
  const len = $("sg-observaciones").value.trim().length;
  const counter = $("sg-counter");
  counter.textContent = len < COMENTARIO_PROVEEDOR_MINIMO
    ? `${len} / 1500 (mínimo ${COMENTARIO_PROVEEDOR_MINIMO} caracteres)`
    : `${len} / 1500`;
  counter.classList.toggle("limit", len < COMENTARIO_PROVEEDOR_MINIMO || len >= 1500);
}

async function registrarSeguimiento() {
  if (!registroActual) return;
  const comentario = $("sg-observaciones").value.trim();
  if (!comentario) { toast("El seguimiento no puede estar vacío.", "error"); return; }
  if (comentario.length < COMENTARIO_PROVEEDOR_MINIMO) {
    toast(`Las observaciones deben tener al menos ${COMENTARIO_PROVEEDOR_MINIMO} caracteres (llevas ${comentario.length}).`, "error");
    return;
  }

  // El comprobante solo se exige hasta la segunda vuelta, cuando Cabina ya
  // regresó el expediente como "Seguimiento de Cita" (ver cargarPagoAnticipado).
  const necesitaComprobante = pagoAnticipadoActual.es_anticipado && registroActual.estatus === "Seguimiento de Cita"
    && esPerfilProveedor();
  const archivoComprobante = $("sg-comprobante-input").files[0];
  if (necesitaComprobante) {
    if (!archivoComprobante) {
      toast("Debes subir el comprobante de pago antes de continuar.", "error");
      return;
    }
    if (!COMPROBANTE_TIPOS_PERMITIDOS.includes(archivoComprobante.type)) {
      toast("Formato no permitido. Solo se aceptan PDF, JPG o PNG.", "error");
      return;
    }
    if (archivoComprobante.size > COMPROBANTE_TAMANO_MAXIMO) {
      toast("El comprobante supera el máximo permitido de 5 MB.", "error");
      return;
    }
  }

  const btn = $("sg-actualizar-btn");
  btn.disabled = true;
  let exito = false;
  try {
    if (necesitaComprobante) {
      const formData = new FormData();
      formData.append("cl_expediente", registroActual.expediente);
      formData.append("archivo", archivoComprobante);
      await api("/seguimiento/comprobante", { method: "POST", formData });
    }

    await api("/seguimiento/actualizar", {
      method: "POST",
      body: { cl_expediente: registroActual.expediente, comentario },
    });
    exito = true;
    toast("Seguimiento registrado en Core.", "success");
    // Confirmación visible y permanente en pantalla (no solo el toast, que desaparece):
    // se deja el mensaje enviado a la vista, bloqueado, como comprobante.
    $("sg-exito-banner").classList.remove("hidden");
    $("sg-observaciones").disabled = true;
    $("sg-cancelar-btn").disabled = true;
    $("sg-comprobante-input").disabled = true;

    // El backend ya movió el estatus a "Seguimiento Proveedor" — hay que
    // reflejarlo también en los datos que ya tienen las demás pantallas, si
    // no el expediente se sigue viendo en la lista hasta refrescar la página.
    registroActual.estatus = "Seguimiento Proveedor";
    notificarCambioEstatus(registroActual.expediente, "Seguimiento Proveedor");

    // Para que el comentario recién enviado se vea de inmediato en
    // "Comentarios del Proveedor", sin tener que refrescar la página.
    cargarComentarios(registroActual.expediente);
    // Refresca el comprobante y la casilla de pago anticipado (ya queda
    // bloqueada tras este primer/segundo envío, ver backend).
    cargarPagoAnticipado(registroActual);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    if (!exito) btn.disabled = false; // si tuvo éxito, se queda deshabilitado a propósito
  }
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;

  $("sg-buscar-btn").addEventListener("click", buscarExpediente);
  $("sg-buscar-expediente").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); buscarExpediente(); }
  });
  $("ig-pago-anticipado").addEventListener("change", cambiarPagoAnticipado);
  $("sg-estatus").addEventListener("change", (e) => {
    $("sg-motivo-regreso-field").classList.toggle("hidden", !ESTATUS_DE_REGRESO.includes(e.target.value));
    actualizarTextoMotivoRegreso(e.target.value);
  });
  $("sg-estatus-btn").addEventListener("click", actualizarEstatus);
  $("sg-observaciones").addEventListener("input", actualizarContador);
  $("sg-actualizar-btn").addEventListener("click", registrarSeguimiento);
  $("sg-cancelar-btn").addEventListener("click", () => {
    $("sg-observaciones").value = "";
    actualizarContador();
    toast("Cambios descartados.");
  });
  $("sg-regresar-btn").addEventListener("click", () => navegar("expedientes"));
}

export function aplicarPermisos() {
  // Cabina no tiene acceso a "Registrar seguimiento" (eso es exclusivo de Proveedor).
  $("sg-seguimiento-card").classList.toggle("hidden-perfil", esPerfilCabina());
  // Proveedor no puede cambiar el estado a mano ("Estado del Caso"): en su
  // caso el estatus solo cambia automático al usar "Actualizar Core".
  $("sg-estatus-card").classList.toggle("hidden-perfil", esPerfilProveedor());
}

export function alEntrar() {
  const input = $("sg-buscar-expediente");
  if (!input.disabled && !$("sg-buscar-card").classList.contains("hidden")) input.focus();
}

export function reiniciar() {
  $("sg-buscar-card").classList.remove("hidden");
  $("sg-buscar-expediente").disabled = false;
  $("sg-buscar-expediente").value = "";
  ocultarPaneles();
}
