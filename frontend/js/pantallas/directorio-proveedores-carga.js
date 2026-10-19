/* Pantalla: Directorio de Proveedores -- Carga catálogo proveedores
   (submenú de Directorio de Proveedores, exclusiva de Administrador). La
   configuración y los datos de este padrón viven SOLO en este portal
   (SQLite local) -- no hay conexión a SQL Server para esto.

   La carga es INCREMENTAL (decisión del usuario, 2026-10-19): agrega los
   proveedores que no existan y actualiza los que ya estaban, sin tocarles
   su clave -- si la clave cambiara, las citas ya agendadas apuntarían a
   otro médico. */
import { api, apiArchivo } from "../core/api.js";
import { toast } from "../core/toast.js";
import { formatDateTime } from "../core/formato.js";

const PLANTILLA = `
  <div class="card tono-azul">
    <div class="card-header"><h2>Carga del catálogo de proveedores</h2></div>
    <div class="card-body">
      <p>
        Este catálogo se administra únicamente desde este portal. Cada
      archivo que subas <b>agrega los proveedores nuevos y actualiza los
      que ya estaban</b>, sin borrar el resto: puedes mandar solo los
      nuevos o el padrón completo, en ambos casos funciona.
    </p>
    <p class="hint">
      A cada proveedor el portal le asigna su propia clave (PRV-000001) y
      se la conserva entre cargas, para no perder el control de las citas
      que ya se le hayan generado. Un médico dado de alta aquí pasa a
      «Dentro de la red» en cuanto llega en una de estas cargas.
    </p>
      <div class="actions-row" style="justify-content:flex-start;">
        <button class="btn btn-secondary" id="cp-descargar-plantilla">Descargar plantilla Excel</button>
      </div>
      <div class="field" style="max-width:420px;margin-top:16px;">
        <label for="cp-archivo">Archivo Excel (.xlsx) con los proveedores</label>
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
    if (!ultima) {
      $("cp-resumen").textContent = "Todavía no se ha cargado ningún catálogo.";
      return;
    }
    $("cp-resumen").textContent =
      `Padrón actual: ${data.total} proveedor(es) -- ${data.dentro_de_la_red} dentro de la red y ` +
      `${data.fuera_de_la_red} fuera de la red. Última carga el ${formatDateTime(ultima.fecha)} ` +
      `(${ultima.rfc}): ${ultima.nuevos} nuevo(s), ${ultima.actualizados} actualizado(s)` +
      (ultima.absorbidos ? `, ${ultima.absorbidos} que ya estaban dados de alta en el portal` : "") + ".";
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
    const absorbidos = data.absorbidos ? `, ${data.absorbidos} que ya estaban dados de alta aquí` : "";
    toast(
      `Catálogo cargado: ${data.nuevos} nuevo(s), ${data.actualizados} actualizado(s)${absorbidos}.`,
      "success"
    );
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
