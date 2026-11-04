/* Contador "Correos de hoy: X de 100" (tope diario de la cuenta de correo,
   ver app/services/cuota_correos_service.py). Lo ven Cabina (junto a "Enviar
   correo a proveedores") y Administrador (junto a "Generar corte" y al
   enviar el corte). Todos los contadores de la página se pintan juntos: basta
   con poner cuotaCorreosHtml() donde se quiera mostrar. */
import { api } from "../core/api.js";

export function cuotaCorreosHtml(id) {
  return `<span class="cuota-correos" id="${id}" role="status" title="Tope de correos que el portal puede enviar por día"></span>`;
}

export function pintarCuotaCorreos(cuota) {
  document.querySelectorAll(".cuota-correos").forEach(el => {
    el.textContent = `Correos de hoy: ${cuota.usados} de ${cuota.limite}`;
    el.classList.toggle("aviso", cuota.nivel === "aviso");
    el.classList.toggle("agotado", cuota.nivel === "agotado");
  });
}

/* Pide el contador al servidor y lo pinta. Regresa el dato (o null si no se
   pudo): quien llama decide si sigue sin él. */
export async function actualizarCuotaCorreos() {
  try {
    const cuota = await api("/correos-enviados/cuota");
    pintarCuotaCorreos(cuota);
    return cuota;
  } catch (err) {
    console.warn("No se pudo consultar el contador de correos:", err.message);
    return null;
  }
}
