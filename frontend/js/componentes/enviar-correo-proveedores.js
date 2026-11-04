/* "Enviar correo a proveedores" (pantallas Expedientes y Expedientes PA).

   Cerca del tope diario de correos el servidor no envía nada en el primer
   intento: responde requiere_confirmacion con el aviso. Si la persona acepta,
   se vuelve a mandar la misma selección con confirmar_limite. Al llegar al
   tope, el envío sigue (los expedientes pasan a "En Espera de Respuesta"),
   solo que sin correo. Ver app/services/envio_correo_service.py. */
import { api } from "../core/api.js";
import { toast } from "../core/toast.js";
import { confirmar } from "./confirmar.js";
import { actualizarCuotaCorreos } from "./cuota-correos.js";

/* Regresa la respuesta final del servidor, o null si se canceló o falló
   (en ese caso ya se mostró el aviso). */
export async function enviarCorreoAProveedores(expedientes) {
  try {
    let data = await api("/expedientes/enviar-correo-proveedores", {
      method: "POST",
      body: { expedientes },
    });
    if (data.requiere_confirmacion) {
      const seguir = await confirmar({
        titulo: "Límite de correos por día",
        mensaje: data.mensaje,
        textoConfirmar: "Continuar",
      });
      if (!seguir) return null;
      data = await api("/expedientes/enviar-correo-proveedores", {
        method: "POST",
        body: { expedientes, confirmar_limite: true },
      });
    }
    toast(data.mensaje, data.correo_enviado ? "success" : "aviso", 8000);
    return data;
  } catch (err) {
    toast(err.message, "error", 8000);
    return null;
  } finally {
    actualizarCuotaCorreos();
  }
}
