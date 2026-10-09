/* Pantalla: Historial de correos a proveedores (solo Administrador).
   Evidencia de qué se mandó, a quién, cuándo y quién le dio clic -- para
   cuando un proveedor dice que nunca se le notificó un expediente. */
import { api } from "../core/api.js";
import { escapeHtml, formatDateTime } from "../core/formato.js";
import { toast } from "../core/toast.js";
import { limitarADigitos } from "../componentes/campo-numerico.js";

const PLANTILLA = `
  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Historial de correos a proveedores</h2>
    </div>
    <div class="card-body">
      <div class="filters-grid">
        <div class="field">
          <label for="hc-expediente">Expediente (opcional)</label>
          <input type="text" id="hc-expediente" inputmode="numeric" placeholder="Número de expediente">
        </div>
      </div>
      <div class="filters-actions">
        <button class="btn btn-primary" id="hc-btn-buscar">Buscar</button>
        <button class="btn btn-secondary" id="hc-btn-ver-todos">Ver todos</button>
      </div>
    </div>
  </div>

  <div class="card tono-verdeazul">
    <div class="card-header">
      <h2>Resultados (<span id="hcCount">0</span>)</h2>
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr>
            <th style="width:150px;">Fecha</th>
            <th style="width:110px;">Tipo</th>
            <th>Expediente(s)</th>
            <th>Destinatario</th>
            <th style="width:160px;">Enviado por</th>
            <th style="width:100px;">Real / Prueba</th>
          </tr>
        </thead>
        <tbody id="hc-tbody"></tbody>
      </table>
    </div>
  </div>`;

const $ = (id) => document.getElementById(id);

const ETIQUETA_TIPO = { nuevo: "Nuevo", recordatorio: "Recordatorio" };

function renderFilas(registros) {
  $("hcCount").textContent = registros.length;
  if (registros.length === 0) {
    $("hc-tbody").innerHTML = `<tr><td colspan="6" class="empty">No hay correos registrados.</td></tr>`;
    return;
  }
  $("hc-tbody").innerHTML = registros.map(r => `
    <tr>
      <td>${formatDateTime(r.fecha)}</td>
      <td>${ETIQUETA_TIPO[r.tipo] || escapeHtml(r.tipo)}</td>
      <td>${r.expedientes.join(", ")}</td>
      <td>${escapeHtml(r.destinatario)}</td>
      <td>${escapeHtml(r.nombre_envio)}</td>
      <td>${r.simulado ? "Prueba (sin SMTP)" : "Real"}</td>
    </tr>
  `).join("");
}

async function buscar() {
  const clExpediente = $("hc-expediente").value.trim();
  try {
    const params = clExpediente ? { cl_expediente: clExpediente } : {};
    const data = await api("/correos-enviados", { params });
    renderFilas(data);
  } catch (err) {
    toast(err.message, "error");
  }
}

export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  limitarADigitos($("hc-expediente"), 10);
  $("hc-btn-buscar").addEventListener("click", buscar);
  $("hc-btn-ver-todos").addEventListener("click", () => {
    $("hc-expediente").value = "";
    buscar();
  });
  $("hc-expediente").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); buscar(); }
  });
}

export function alEntrar() {
  buscar();
}
