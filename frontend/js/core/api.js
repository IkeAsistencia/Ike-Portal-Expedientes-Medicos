/* Cliente HTTP del portal. El frontend lo sirve el mismo FastAPI (ver
   app/main.py), así que todas las rutas son relativas al mismo origen: no
   hace falta configurar URL ni CORS. */
import { getToken } from "./sesion.js";

function construirUrl(path, params) {
  let url = path;
  if (params) {
    const usp = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null || v === "") return;
      if (Array.isArray(v)) v.forEach((item) => usp.append(k, item));
      else usp.append(k, v);
    });
    const qs = usp.toString();
    if (qs) url += "?" + qs;
  }
  return url;
}

function headersAuth() {
  const token = getToken();
  return token ? { Authorization: "Bearer " + token } : {};
}

export async function api(path, opts = {}) {
  const { method = "GET", params, body, formData, auth = true } = opts;

  const headers = auth ? headersAuth() : {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // formData: NO se pone Content-Type a mano -- el navegador arma el boundary
  // del multipart solo, si tú lo defines a mano queda mal formado.

  let res;
  try {
    res = await fetch(construirUrl(path, params), {
      method,
      headers,
      body: formData !== undefined ? formData : (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (networkErr) {
    throw new Error("No se pudo conectar con el servidor. Verifica que esté corriendo.");
  }

  let data = null;
  try { data = await res.json(); } catch (e) { /* respuesta sin body */ }

  if (!res.ok) {
    if (res.status === 401 && auth) {
      // app.js escucha este evento y cierra la sesión (así este módulo no
      // depende de la pantalla de login).
      window.dispatchEvent(new CustomEvent("sesion-expirada"));
    }
    const detail = data && data.detail;
    let msg = "Error " + res.status;
    if (typeof detail === "string") msg = detail;
    else if (Array.isArray(detail) && detail.length) msg = detail.map(d => d.msg || JSON.stringify(d)).join(" | ");
    throw new Error(msg);
  }
  return data;
}

/* Descarga un archivo protegido (Excel del corte, comprobante de pago).
   Regresa el blob y el nombre que mandó el servidor en Content-Disposition. */
export async function apiArchivo(path, mensajeError) {
  const res = await fetch(path, { headers: headersAuth() });
  if (!res.ok) throw new Error(mensajeError);
  const blob = await res.blob();
  const disposicion = res.headers.get("Content-Disposition") || "";
  const match = disposicion.match(/filename="?([^"]+)"?/);
  return { blob, nombreArchivo: match ? match[1] : null };
}
