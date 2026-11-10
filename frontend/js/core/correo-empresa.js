/* Candado de dominio: el correo de un Proveedor y el destinatario del corte
   solo pueden ser de la empresa. Mismo criterio y mismo aviso que el
   servidor (app/core/correo_empresa.py), para avisar antes de enviar. */
export const DOMINIO_EMPRESA = "ikeasistencia.com";
export const MENSAJE_DOMINIO_NO_PERMITIDO =
  `El correo que acabas de ingresar no pertenece al dominio de @${DOMINIO_EMPRESA}.`;

export function esCorreoDeEmpresa(correo) {
  const partes = (correo || "").trim().toLowerCase().split("@");
  return partes.length === 2 && partes[0] !== "" && partes[1] === DOMINIO_EMPRESA;
}
