/* Pantalla: Directorio de Proveedores -- Carga catálogo proveedores Core
   (submenú de Directorio de Proveedores, exclusiva de Administrador). La
   configuración y los datos de este catálogo viven SOLO en este portal
   (SQLite local) -- no hay conexión a SQL Server/Core para esto. Cada
   carga REEMPLAZA el catálogo completo: el Excel debe traer siempre
   TODOS los proveedores, no solo los nuevos. */
import { api, apiArchivo } from "../core/api.js";
import { toast } from "../core/toast.js";
import { formatDateTime } from "../core/formato.js";

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2>Carga del catálogo de proveedores (Core)</h2></div>
    <div class="card-body">
      <p>
        Este catálogo alimenta el Directorio de Proveedores y vive únicamente
        en este portal, no en SQL Server. Cada archivo que subas
        <b>reemplaza por completo</b> el catálogo anterior: debe traer a
        TODOS los proveedores, no solo los nuevos.
      </p>
      <div class="actions-row" style="justify-content:flex-start;">
        <button class="btn btn-secondary" id="cp-descargar-plantilla">Descargar plantilla Excel</button>
      </div>
      <div class="field" style="max-width:420px;margin-top:16px;">
        <label for="cp-archivo">Archivo Excel (.xlsx) con el catálogo completo</label>
        <input type="file" id="cp-archivo" accept=".xlsx">
      </div>
      <div class="actions-row" style="justify-content:flex-start;">
        <button class="btn btn-primary" id="cp-cargar">Cargar catálogo</button>
      </div>
      <p class="hint" id="cp-resumen"></p>
    </div>
  </div>`;

const $ = (id) => document.getElementById(id);

async function descargarPlantilla() {
  const btn = $("cp-descargar-plantilla");
  btn.disabled = true;
  try {
    const { blob, nombreArchivo } = await apiArchivo(
      "/proveedores-catalogo/plantilla",
      "No se pudo descargar la plantilla."
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombreArchivo || "plantilla_catalogo_proveedores.xlsx";
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

async function cargarResumen() {
  try {
    const data = await api("/proveedores-catalogo");
    const ultima = data.ultima_carga;
    $("cp-resumen").textContent = ultima
      ? `Catálogo actual: ${data.total} proveedor(es) -- última carga el ${formatDateTime(ultima.fecha)} (${ultima.rfc}).`
      : "Todavía no se ha cargado ningún catálogo.";
  } catch (err) {
    $("cp-resumen").textContent = "";
  }
}

async function cargarArchivo() {
  const input = $("cp-archivo");
  const archivo = input.files[0];
  if (!archivo) { toast("Selecciona un archivo Excel (.xlsx) primero.", "error"); return; }

  const btn = $("cp-cargar");
  btn.disabled = true;
  try {
    const formData = new FormData();
    formData.append("archivo", archivo);
    const data = await api("/proveedores-catalogo/cargar", { method: "POST", formData });
    toast(`Catálogo cargado: ${data.total} proveedor(es).`, "success");
    input.value = "";
    cargarResumen();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  $("cp-descargar-plantilla").addEventListener("click", descargarPlantilla);
  $("cp-cargar").addEventListener("click", cargarArchivo);
}

export function alEntrar() {
  cargarResumen();
}
