/* Modal: Corte de expedientes (Excel).
   Botón "Generar corte" -- exclusivo del perfil Administrador, independiente
   de "Enviar correo a proveedores": este no avisa al proveedor ni cambia
   estatus, es la evidencia/corte que Admin puede descargar/previsualizar
   antes de decidir enviarlo. Todos los seleccionados deben compartir el
   mismo estatus (el backend también lo valida, ver routers/expedientes.py).

   El corte es para Cabina, no para proveedores: se envía a UNA sola
   dirección que el Administrador escribe en "Enviar a". Enviarlo es
   opcional (descargar el Excel también basta) y cuenta contra el tope
   diario de correos. */
import { api, apiArchivo } from "../core/api.js";
import { escapeHtml, formatDate } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { confirmar as confirmarAviso } from "../componentes/confirmar.js";
import { actualizarCuotaCorreos, cuotaCorreosHtml } from "../componentes/cuota-correos.js";
import { crearModal } from "../componentes/modal.js";

// Mismo patrón que el servidor (revisar_correo en
// app/services/validacion_rfc_cedula_service.py), para avisar antes de enviar.
const PATRON_CORREO = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$/;

let modal = null;
let corteActual = null; // { corte_id, alConfirmar }

const $ = (id) => document.getElementById(id);

function obtenerModal() {
  if (modal) return modal;
  modal = crearModal({
    id: "corte-modal-overlay",
    titulo: "Corte de expedientes",
    cuerpo: `
      <p id="corte-modal-resumen"></p>
      <div class="table-wrap" style="max-height:320px;overflow:auto;">
        <table class="mini-table-corte">
          <thead><tr><th>Expediente</th><th>Cuenta</th><th>Paciente</th><th>Fecha Apertura</th></tr></thead>
          <tbody id="corte-modal-tbody"></tbody>
        </table>
      </div>
      <div class="corte-envio">
        <div class="field">
          <label for="corte-modal-destinatario">Enviar a (opcional)</label>
          <input type="email" id="corte-modal-destinatario" maxlength="120" autocomplete="email"
                 placeholder="correo@ikeasistencia.com">
          <span class="corte-envio-ayuda">Una sola dirección. Si no lo vas a enviar, basta con descargar el Excel.</span>
        </div>
        ${cuotaCorreosHtml("corte-cuota-correos")}
      </div>`,
    pie: `
      <button class="btn btn-secondary" id="corte-modal-descargar">Descargar Excel</button>
      <button class="btn btn-primary" id="corte-modal-confirmar">Enviar</button>`,
    alCerrar: () => { corteActual = null; },
  });
  $("corte-modal-descargar").addEventListener("click", descargar);
  $("corte-modal-confirmar").addEventListener("click", confirmar);
  return modal;
}

/* - tipoExpediente: "normal" | "anticipado"
   - seleccionados: Set de números de expediente marcados
   - fuente: arreglo con los registros completos (para validar y previsualizar)
   - boton: el botón que lo abrió (se deshabilita mientras se genera)
   - alConfirmar(): qué hacer en la pantalla de origen al enviarse el corte */
export async function abrirModalCorte({ tipoExpediente, seleccionados, fuente, boton, alConfirmar }) {
  if (seleccionados.size === 0) {
    toast("Selecciona al menos un expediente para generar el corte.", "error");
    return;
  }
  const estatusSeleccionados = new Set(
    Array.from(seleccionados)
      .map(exp => fuente.find(r => r.expediente === exp))
      .filter(Boolean)
      .map(r => r.estatus)
  );
  if (estatusSeleccionados.size > 1) {
    toast(
      "Todos los expedientes seleccionados deben tener el mismo estatus para generar el corte (seleccionaste: " +
        Array.from(estatusSeleccionados).join(", ") + ").",
      "error"
    );
    return;
  }
  boton.disabled = true;
  try {
    const data = await api("/expedientes/corte", {
      method: "POST",
      body: { expedientes: Array.from(seleccionados), tipo_expediente: tipoExpediente },
    });
    const m = obtenerModal();
    corteActual = { corte_id: data.corte_id, alConfirmar };

    const filas = data.expedientes.map(exp => fuente.find(r => r.expediente === exp)).filter(Boolean);
    const estatusLote = estatusSeleccionados.size ? Array.from(estatusSeleccionados)[0] : "";
    m.ponerTitulo(tipoExpediente === "anticipado" ? "Corte de Expedientes — Pago Anticipado" : "Corte de Expedientes");
    $("corte-modal-resumen").textContent =
      `${data.total} expediente(s) en "${estatusLote}" — archivo: ${data.archivo_nombre}. Descárgalo o previsualízalo antes de confirmar el envío.`;
    $("corte-modal-tbody").innerHTML = filas.map(r => `
      <tr>
        <td>${r.expediente}</td>
        <td>${escapeHtml(r.cuenta)}</td>
        <td>${escapeHtml(r.nombre_paciente)}</td>
        <td>${formatDate(r.fecha_apertura_servicio)}</td>
      </tr>`).join("");
    $("corte-modal-destinatario").value = "";
    actualizarCuotaCorreos();
    m.abrir();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    boton.disabled = false;
  }
}

async function descargar() {
  if (!corteActual) return;
  const btn = $("corte-modal-descargar");
  btn.disabled = true;
  try {
    const { blob, nombreArchivo } = await apiArchivo(
      "/expedientes/corte/" + corteActual.corte_id + "/descargar",
      "No se pudo descargar el corte."
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombreArchivo || "corte.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function confirmar() {
  if (!corteActual) return;
  const campo = $("corte-modal-destinatario");
  const destinatario = campo.value.trim();
  if (!destinatario) {
    toast("Escribe en \"Enviar a\" la dirección de correo a la que se mandará el corte.", "error");
    campo.focus();
    return;
  }
  if (!PATRON_CORREO.test(destinatario)) {
    toast("La dirección de \"Enviar a\" no tiene un formato válido (escribe una sola).", "error");
    campo.focus();
    return;
  }

  const btn = $("corte-modal-confirmar");
  btn.disabled = true;
  try {
    const cuota = await actualizarCuotaCorreos();
    if (cuota && cuota.nivel === "agotado") {
      toast(
        `Se alcanzó el límite de ${cuota.limite} correos por día: el corte no se puede enviar hoy. Puedes descargar el Excel.`,
        "error", 8000
      );
      return;
    }
    if (cuota && cuota.nivel === "aviso") {
      const seguir = await confirmarAviso({
        titulo: "Límite de correos por día",
        mensaje: `Estás a punto de alcanzar el límite de correos por día: van ${cuota.usados} de ${cuota.limite}. ¿Quieres enviar el corte?`,
        textoConfirmar: "Enviar",
      });
      if (!seguir) return;
    }
    const data = await api("/expedientes/corte/" + corteActual.corte_id + "/enviar", {
      method: "POST",
      body: { destinatario },
    });
    toast(
      data.simulado
        ? `Corte simulado para ${data.destinatario} (${data.enviados} expediente(s)) -- falta configurar SMTP real.`
        : `Corte enviado a ${data.destinatario} (${data.enviados} expediente(s)).`,
      "success"
    );
    corteActual.alConfirmar();
    modal.cerrar();
  } catch (err) {
    toast(err.message, "error", 8000);
  } finally {
    btn.disabled = false;
    actualizarCuotaCorreos();
  }
}

export function reiniciar() {
  if (modal) modal.cerrar();
}
